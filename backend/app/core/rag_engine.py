"""
core/rag_engine.py — Full RAG pipeline with SSE streaming.

Implements rag_stream(), an async generator that yields SSE-compatible dicts:
  {"event": "token",   "data": "<chunk>"}
  {"event": "sources", "data": "<JSON array>"}
  {"event": "done",    "data": "[DONE]"}

Pipeline stages:
  1. Query preprocessing (whitespace normalisation)
  2. HyDE — hypothetical-document embedding via Ollama
  3. Multi-query — MULTIQUERY_COUNT reformulations; union + dedup across hybrid_search calls
  4. Reranking via bge-reranker-v2-m3
  5. Fallback guard (no results or max score < 0.3)
  6. Context assembly — expand_to_parents, top-5; chat history from DB
  7. Prompt construction using PROPESQI system prompt template
  8. LLM streaming via Ollama /api/chat
  9. Post-processing — save user + assistant messages; update last_activity
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.reranker import rerank
from app.db.search import expand_to_parents, hybrid_search
from app.models.chat import ChatMessage, ChatSession
from qdrant_client.models import ScoredPoint

logger = logging.getLogger(__name__)

_MODEL = "gemma3:12b"

_FALLBACK_MESSAGE = (
    "Não possuo informações sobre este assunto em minha base de documentos. "
    "Para esclarecimentos adicionais, entre em contato diretamente com a PROPESQI."
)

_SYSTEM_PROMPT = """\
Você é o assistente virtual da Pró-Reitoria de Pesquisa e Inovação (PROPESQI) \
da Universidade Federal do Piauí (UFPI). Responda sempre em português formal \
e de forma clara e objetiva.

REGRAS OBRIGATÓRIAS:
1. Responda EXCLUSIVAMENTE com base nos documentos fornecidos no contexto.
2. Se a informação não estiver nos documentos, responda:
   "Não possuo informações sobre este assunto em minha base de documentos.
    Para esclarecimentos adicionais, entre em contato diretamente com a PROPESQI."
3. Nunca invente datas, normas, nomes ou valores.
4. Ao final de cada resposta, cite as fontes utilizadas (nome do documento e página).
5. Mantenha tom institucional, respeitoso e acessível ao público universitário.

CONTEXTO DOS DOCUMENTOS:
{context}

HISTÓRICO DA CONVERSA:
{chat_history}\
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _ollama_generate(prompt: str, temperature: float, settings) -> str:
    """Call Ollama /api/chat (non-streaming) and return the response text."""
    async with httpx.AsyncClient(timeout=300.0) as http:
        resp = await http.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": _MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        if resp.status_code >= 400:
            logger.error("_ollama_generate: HTTP %s — body: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()


def _build_context(parents: list[dict]) -> str:
    parts = []
    for i, p in enumerate(parents, start=1):
        # Truncate source name to prevent excessively long prompt headers
        source = p.get("source", "desconhecido")[:200]
        page = p.get("page_number") or 0
        text = p.get("parent_text", "")
        header = f"[{i}] {source}" + (f" (p. {page})" if page else "")
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts)


def _build_history(messages: list[ChatMessage]) -> str:
    if not messages:
        return "(sem histórico)"
    parts = []
    for msg in messages:
        role_label = "Usuário" if msg.role == "user" else "Assistente"
        # Truncate each message to avoid context-window overflow from long turns
        text = msg.content[:500]
        parts.append(f"{role_label}: {text}")
    return "\n".join(parts)


def _build_sources(parents: list[dict]) -> list[dict]:
    sources = []
    for p in parents:
        raw_doc_id = p.get("doc_id", "")
        try:
            doc_uuid = str(UUID(str(raw_doc_id)))
        except (ValueError, AttributeError):
            continue
        page = p.get("page_number") or None
        sources.append(
            {
                "doc_id": doc_uuid,
                "original_name": p.get("source", ""),
                "page_number": page if page else None,
                "score": round(float(p.get("score", 0.0)), 4),
            }
        )
    return sources


async def _persist_messages(
    db: AsyncSession,
    session_id: UUID,
    user_query: str,
    assistant_response: str,
    sources: list[dict],
    assistant_id: UUID | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        ChatMessage(
            session_id=session_id,
            role="user",
            content=user_query,
            sources=None,
            created_at=now,
        )
    )
    db.add(
        ChatMessage(
            id=assistant_id if assistant_id is not None else uuid4(),
            session_id=session_id,
            role="assistant",
            content=assistant_response,
            sources=sources if sources else None,
            created_at=now + timedelta(microseconds=1),
        )
    )
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(last_activity=now)
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def rag_stream(
    query: str,
    session_id: UUID,
    db: AsyncSession,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that drives the full RAG pipeline and yields SSE events.

    Yields dicts consumed by sse-starlette's EventSourceResponse:
      {"event": "token",   "data": "<text chunk>"}
      {"event": "sources", "data": "<JSON list of SourceCitation dicts>"}
      {"event": "done",    "data": "[DONE]"}

    Handles asyncio.CancelledError (client disconnect) gracefully: no partial
    DB writes are made; the generator exits cleanly.
    """
    settings = get_settings()
    response_parts: list[str] = []
    reranked_parents: list[dict] = []

    try:
        # Pre-generate the assistant message UUID so the frontend can link
        # feedback requests to the correct DB row before the message is saved.
        assistant_msg_id = uuid4()
        yield {"event": "message_id", "data": str(assistant_msg_id)}

        # ------------------------------------------------------------------ #
        # 1. Query preprocessing                                              #
        # ------------------------------------------------------------------ #
        query = " ".join(query.split())
        # Guard: min_length=1 validates the raw string but all-whitespace input
        # normalises to ""; return fallback without persisting an empty query.
        if not query:
            yield {"event": "token", "data": _FALLBACK_MESSAGE}
            yield {"event": "sources", "data": "[]"}
            yield {"event": "done", "data": "[DONE]"}
            return

        # ------------------------------------------------------------------ #
        # 2. HyDE — hypothetical document embedding                          #
        # ------------------------------------------------------------------ #
        hyde_prompt = (
            f"Escreva uma resposta curta e factual para a seguinte pergunta "
            f"sobre documentos da PROPESQI/UFPI:\n\n{query}"
        )

        # ------------------------------------------------------------------ #
        # 3. Multi-query reformulations (parallel with HyDE via gather)      #
        # ------------------------------------------------------------------ #
        reform_prompt = (
            f"Gere {settings.MULTIQUERY_COUNT} reformulações diferentes da seguinte pergunta para melhorar "
            f"a busca em uma base de documentos acadêmicos. "
            f"Responda apenas com as {settings.MULTIQUERY_COUNT} reformulações, uma por linha, sem numeração.\n\n"
            f"Pergunta original: {query}"
        )
        # Both LLM calls are independent — run concurrently to reduce latency.
        # return_exceptions=True allows graceful degradation: if one call fails,
        # the pipeline continues with whichever results are still valid.
        _llm_results = await asyncio.gather(
            _ollama_generate(hyde_prompt, temperature=settings.HYDE_TEMPERATURE, settings=settings),
            _ollama_generate(reform_prompt, temperature=settings.MULTIQUERY_TEMPERATURE, settings=settings),
            return_exceptions=True,
        )
        hyde_answer = _llm_results[0] if isinstance(_llm_results[0], str) else ""
        reform_text = _llm_results[1] if isinstance(_llm_results[1], str) else ""
        if not isinstance(_llm_results[0], str):
            logger.warning("rag_stream: HyDE LLM call failed — skipping: %s", _llm_results[0])
        if not isinstance(_llm_results[1], str):
            logger.warning("rag_stream: multi-query LLM call failed — skipping reformulations: %s", _llm_results[1])
        extra_queries = [
            line.strip()
            for line in reform_text.splitlines()
            if line.strip()
        ][:settings.MULTIQUERY_COUNT]

        # Original query included in union set (PLANEJAMENTO.md §4.2 step 3)
        all_queries = [query, hyde_answer] + extra_queries  # original + HyDE + reformulations

        # Union + dedup across all queries (keep highest score per point ID)
        merged_by_id: dict[str, ScoredPoint] = {}
        for q in all_queries:
            if not q:
                continue
            pts = await hybrid_search(q, top_k=20)
            for pt in pts:
                pid = str(pt.id)
                existing = merged_by_id.get(pid)
                if existing is None or pt.score > existing.score:
                    merged_by_id[pid] = pt

        merged_points = list(merged_by_id.values())

        # ------------------------------------------------------------------ #
        # 4. Reranking                                                        #
        # ------------------------------------------------------------------ #
        reranked = await rerank(
            query,
            merged_points,
            top_k=settings.RERANKER_TOP_K,
            score_threshold=settings.RERANKER_SCORE_THRESHOLD,
        )

        # ------------------------------------------------------------------ #
        # 5. Fallback guard                                                   #
        # ------------------------------------------------------------------ #
        max_score = max((p.score for p in reranked), default=0.0)
        if not reranked or max_score < 0.3:
            yield {"event": "token", "data": _FALLBACK_MESSAGE}
            yield {"event": "sources", "data": "[]"}
            yield {"event": "done", "data": "[DONE]"}
            await _persist_messages(db, session_id, query, _FALLBACK_MESSAGE, [], assistant_id=assistant_msg_id)
            return

        # ------------------------------------------------------------------ #
        # 6. Context assembly                                                 #
        # ------------------------------------------------------------------ #
        reranked_parents = expand_to_parents(reranked)[:5]

        history_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        )
        history_msgs = list(reversed(history_result.scalars().all()))

        # ------------------------------------------------------------------ #
        # 7. Prompt construction                                              #
        # ------------------------------------------------------------------ #
        context_text = _build_context(reranked_parents)
        chat_history_text = _build_history(history_msgs)
        system_content = _SYSTEM_PROMPT.format(
            context=context_text,
            chat_history=chat_history_text,
        )

        messages: list[dict] = [{"role": "system", "content": system_content}]
        for msg in history_msgs:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": query})

        # ------------------------------------------------------------------ #
        # 8. LLM streaming                                                    #
        # ------------------------------------------------------------------ #
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as http:
            async with http.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": _MODEL,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.1, "num_predict": 1024},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token: str = chunk.get("message", {}).get("content", "")
                    if token:
                        response_parts.append(token)
                        yield {"event": "token", "data": token}
                    if chunk.get("done"):
                        break

        # ------------------------------------------------------------------ #
        # 9. Post-processing                                                  #
        # ------------------------------------------------------------------ #
        sources_data = _build_sources(reranked_parents)
        full_response = "".join(response_parts)

        yield {"event": "sources", "data": json.dumps(sources_data)}
        yield {"event": "done", "data": "[DONE]"}

        # Persist only after both terminal events have been yielded.
        # Wrap separately so a DB failure does not raise after the stream is closed.
        try:
            await _persist_messages(db, session_id, query, full_response, sources_data, assistant_id=assistant_msg_id)
        except Exception:
            logger.error("rag_stream: failed to persist messages for session %s", session_id)

    except asyncio.CancelledError:
        # Client disconnected mid-stream — exit without writing partial data
        pass
    except Exception:
        # Unexpected error (Ollama down, network failure, etc.) — send error event
        # so the client does not hang waiting for 'done'.
        logger.error("rag_stream: unhandled error for session %s", session_id, exc_info=True)
        yield {"event": "error", "data": "Ocorreu um erro interno. Por favor, tente novamente."}
        yield {"event": "done", "data": "[DONE]"}
