"""
db/reranker.py — Cross-encoder reranking for RAG pipeline step 5.

Wraps BAAI/bge-reranker-v2-m3 (sentence-transformers CrossEncoder) behind a
lazy, thread-safe singleton so the model is loaded only once per process.
Exposes a single public async function: rerank(), which offloads the
synchronous CrossEncoder.predict() call to a thread-pool executor.
"""

import asyncio
import threading
from typing import Optional

from qdrant_client.models import ScoredPoint

from app.core.config import get_settings

# ------------------------------------------------------------------ #
# Lazy singleton — initialised on first call, reused thereafter       #
# ------------------------------------------------------------------ #
_encoder_lock = threading.Lock()
_encoder = None  # type: ignore[assignment]


def _get_encoder():
    """Return the CrossEncoder singleton, loading it on first access."""
    global _encoder
    if _encoder is None:
        with _encoder_lock:
            if _encoder is None:
                # Import deferred so the module is importable before the
                # sentence-transformers package downloads model weights.
                from sentence_transformers import CrossEncoder  # type: ignore[import]

                settings = get_settings()
                _encoder = CrossEncoder(settings.RERANKER_MODEL)
    return _encoder


# ------------------------------------------------------------------ #
# Public interface                                                     #
# ------------------------------------------------------------------ #

async def rerank(
    query: str,
    points: list[ScoredPoint],
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
) -> list[ScoredPoint]:
    """
    Rerank a list of ScoredPoints using the cross-encoder model.

    Args:
        query: The original search query string.
        points: Candidate ScoredPoints from hybrid_search (up to 20).
        top_k: Maximum results to return; defaults to RERANKER_TOP_K setting.
        score_threshold: Minimum rerank score; defaults to RERANKER_SCORE_THRESHOLD.

    Returns:
        Up to top_k ScoredPoints sorted by rerank score descending, with
        the rerank score stored in each point's payload under "rerank_score".
        Points below score_threshold are excluded.
    """
    # a) Return unchanged if list is empty
    if not points:
        return points

    settings = get_settings()
    if top_k is None:
        top_k = settings.RERANKER_TOP_K
    if score_threshold is None:
        score_threshold = settings.RERANKER_SCORE_THRESHOLD

    # b) Extract text from each point's payload for scoring
    texts = [point.payload.get("text", "") if point.payload else "" for point in points]
    pairs = [(query, text) for text in texts]

    # c) Offload synchronous predict() to a thread-pool executor.
    #    _get_encoder() is also called inside the thread so that model
    #    initialisation (potentially blocking for ~seconds on first run)
    #    never stalls the event loop.
    def _predict(query_text_pairs: list[tuple[str, str]]) -> list[float]:
        return _get_encoder().predict(query_text_pairs)

    scores: list[float] = await asyncio.to_thread(_predict, pairs)

    # d/e/f) Apply threshold, sort, cap at top_k, and attach rerank_score
    scored_pairs = list(zip(points, scores))
    scored_pairs = [(pt, float(sc)) for pt, sc in scored_pairs if float(sc) >= score_threshold]
    scored_pairs.sort(key=lambda x: x[1], reverse=True)
    scored_pairs = scored_pairs[:top_k]

    result: list[ScoredPoint] = []
    for point, score in scored_pairs:
        # Build an updated payload and return a new ScoredPoint via model_copy
        # so the original objects passed in by the caller are never mutated.
        new_payload = dict(point.payload) if point.payload else {}
        new_payload["rerank_score"] = score
        result.append(point.model_copy(update={"payload": new_payload}))

    return result
