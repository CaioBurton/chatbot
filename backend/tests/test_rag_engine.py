import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from qdrant_client.models import ScoredPoint

from app.core import rag_engine
from app.db import reranker as reranker_module


def _make_scored_point(score: float) -> ScoredPoint:
    return ScoredPoint(
        id="chunk-1",
        version=1,
        score=score,
        payload={
            "text": "PIBIC e um programa institucional.",
            "text_preview": "PIBIC e um programa institucional.",
            "parent_text": "PIBIC e um programa institucional.",
            "parent_id": "parent-1",
            "doc_id": str(uuid4()),
            "source": "edital.pdf",
            "display_name": "Edital PIBIC",
            "page_number": 3,
            "chunk_index": 0,
        },
    )


async def test_rag_stream_does_not_fallback_when_reranker_returns_results(monkeypatch):
    point = _make_scored_point(score=0.05)

    monkeypatch.setattr(
        rag_engine,
        "get_settings",
        lambda: SimpleNamespace(
            MULTIQUERY_COUNT=0,
            HYDE_TEMPERATURE=0.0,
            MULTIQUERY_TEMPERATURE=0.0,
            OLLAMA_BASE_URL="http://ollama.test",
            CONTEXTUAL_COMPRESSION_ENABLED=False,
        ),
    )

    async def _fake_get_rag_config(_db):
        return SimpleNamespace(
            search_top_k=20,
            search_score_threshold=0.0,
            reranker_top_k=5,
            reranker_score_threshold=0.5,
        )

    async def _fake_hybrid_search(*args, **kwargs):
        return [point]

    async def _fake_rerank(*args, **kwargs):
        reranked_point = point.model_copy(
            update={
                "payload": {**point.payload, "rerank_score": 0.91},
                "score": 0.91,
            }
        )
        return [reranked_point]

    async def _fake_generate(*args, **kwargs):
        return ""

    async def _fake_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(rag_engine, "get_rag_config", _fake_get_rag_config)
    monkeypatch.setattr(rag_engine, "hybrid_search", _fake_hybrid_search)
    monkeypatch.setattr(rag_engine, "rerank", _fake_rerank)
    monkeypatch.setattr(rag_engine, "_ollama_generate", _fake_generate)
    monkeypatch.setattr(rag_engine, "_persist_messages", _fake_persist)

    class _FakeStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield json.dumps({"message": {"content": "Resposta grounded."}})
            yield json.dumps({"done": True})

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return _FakeStreamResponse()

    monkeypatch.setattr(rag_engine.httpx, "AsyncClient", _FakeAsyncClient)

    history_result = MagicMock()
    history_scalars = MagicMock()
    history_scalars.all.return_value = []
    history_result.scalars.return_value = history_scalars

    db = AsyncMock()
    db.execute.return_value = history_result

    events = []
    async for event in rag_engine.rag_stream("O que e PIBIC?", uuid4(), db):
        events.append(event)

    token_events = [event for event in events if event["event"] == "token"]
    assert token_events
    assert token_events[0]["data"] == "Resposta grounded."
    assert all(event["data"] != rag_engine._FALLBACK_MESSAGE for event in token_events)

    sources_event = next(event for event in events if event["event"] == "sources")
    sources = json.loads(sources_event["data"])
    assert sources
    assert sources[0]["score"] == 0.91
    assert sources[0]["display_name"] == "Edital PIBIC"


async def test_rerank_replaces_point_score_with_rerank_score(monkeypatch):
    point = _make_scored_point(score=0.07)

    class _FakeEncoder:
        def predict(self, pairs):
            assert pairs == [("PIBIC", "PIBIC e um programa institucional.")]
            return [0.88]

    monkeypatch.setattr(reranker_module, "_get_encoder", lambda: _FakeEncoder())
    monkeypatch.setattr(
        reranker_module,
        "get_settings",
        lambda: SimpleNamespace(RERANKER_TOP_K=5, RERANKER_SCORE_THRESHOLD=0.5),
    )

    reranked = await reranker_module.rerank("PIBIC", [point])

    assert len(reranked) == 1
    expected_score = reranker_module._sigmoid(0.88)
    assert reranked[0].score == expected_score
    assert reranked[0].payload["rerank_score"] == expected_score
    assert point.score == 0.07


async def test_rerank_threshold_uses_normalized_score(monkeypatch):
    point = _make_scored_point(score=0.07)

    class _FakeEncoder:
        def predict(self, pairs):
            assert pairs == [("o que e pibic?", "PIBIC e um programa institucional.")]
            return [0.003]

    monkeypatch.setattr(reranker_module, "_get_encoder", lambda: _FakeEncoder())
    monkeypatch.setattr(
        reranker_module,
        "get_settings",
        lambda: SimpleNamespace(RERANKER_TOP_K=5, RERANKER_SCORE_THRESHOLD=0.5),
    )

    reranked = await reranker_module.rerank("o que e pibic?", [point])

    assert len(reranked) == 1
    assert reranked[0].score > 0.5


async def test_rerank_uses_text_preview_when_text_is_missing(monkeypatch):
    point = ScoredPoint(
        id="chunk-2",
        version=1,
        score=0.07,
        payload={
            "text_preview": "PIBIC e um programa institucional.",
            "parent_text": "PIBIC e um programa institucional com detalhes adicionais.",
            "parent_id": "parent-2",
            "doc_id": str(uuid4()),
            "source": "edital-preview.pdf",
            "page_number": 1,
            "chunk_index": 1,
        },
    )

    class _FakeEncoder:
        def predict(self, pairs):
            assert pairs == [("o que e pibic?", "PIBIC e um programa institucional.")]
            return [0.9]

    monkeypatch.setattr(reranker_module, "_get_encoder", lambda: _FakeEncoder())
    monkeypatch.setattr(
        reranker_module,
        "get_settings",
        lambda: SimpleNamespace(RERANKER_TOP_K=5, RERANKER_SCORE_THRESHOLD=0.5),
    )

    reranked = await reranker_module.rerank("o que e pibic?", [point])

    assert len(reranked) == 1
    assert reranked[0].score == reranker_module._sigmoid(0.9)