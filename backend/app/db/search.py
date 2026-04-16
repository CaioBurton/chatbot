"""
db/search.py — Hybrid dense+sparse search using Qdrant RRF fusion.

New file. Implements hybrid_search() as a pure DB-layer function (no HTTP endpoints here).
Dense embedding via Ollama bge-m3; sparse via BM42 (app.ingestion.sparse). Both prefetch
lists are fused with Reciprocal Rank Fusion (RRF) inside Qdrant. Top-K defaults to 20.
Returns raw ScoredPoint list; callers are responsible for formatting.

Note: the `payload_filter` parameter is named to avoid shadowing the Python built-in `filter`.
"""

from typing import Optional

import httpx
from qdrant_client.models import Filter, Fusion, FusionQuery, Prefetch, ScoredPoint

from app.core.config import get_settings
from app.db.qdrant import COLLECTION_NAME, DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, get_qdrant_client
from app.ingestion.sparse import encode_sparse


async def hybrid_search(
    query: str,
    top_k: int = 20,
    score_threshold: float = 0.0,
    payload_filter: Optional[Filter] = None,
) -> list[ScoredPoint]:
    """
    Perform a hybrid dense+sparse search with RRF fusion.

    Args:
        query: The search query string.
        top_k: Maximum number of results to return (1–100).
        score_threshold: Minimum score; 0.0 means no filtering.
        payload_filter: Optional Qdrant payload filter to apply.

    Returns:
        List of ScoredPoint objects ordered by RRF score (descending).
    """
    settings = get_settings()

    # ------------------------------------------------------------------ #
    # 1. Dense embedding via Ollama bge-m3                                #
    # ------------------------------------------------------------------ #
    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            f"{settings.OLLAMA_BASE_URL}/api/embed",
            json={"model": "bge-m3", "input": [query]},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        try:
            dense_vector: list[float] = data["embeddings"][0]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(
                f"Unexpected Ollama /api/embed response structure: {data}"
            ) from exc

    # ------------------------------------------------------------------ #
    # 2. Sparse embedding via BM42                                        #
    # ------------------------------------------------------------------ #
    sparse_list = await encode_sparse([query])
    if not sparse_list:
        raise RuntimeError("BM42 encoder returned no sparse vector for query")
    sparse_vector = sparse_list[0]

    # ------------------------------------------------------------------ #
    # 3. Hybrid search with RRF fusion                                    #
    # ------------------------------------------------------------------ #
    qdrant = get_qdrant_client()

    kwargs: dict = {}
    if payload_filter is not None:
        kwargs["query_filter"] = payload_filter
    if score_threshold > 0.0:
        kwargs["score_threshold"] = score_threshold

    result = await qdrant.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            Prefetch(query=dense_vector, using=DENSE_VECTOR_NAME, limit=top_k),
            Prefetch(query=sparse_vector, using=SPARSE_VECTOR_NAME, limit=top_k),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        **kwargs,
    )

    return result.points
