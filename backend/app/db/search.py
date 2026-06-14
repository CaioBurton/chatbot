"""
db/search.py — Hybrid dense+sparse search using Qdrant RRF fusion.

New file. Implements hybrid_search() as a pure DB-layer function (no HTTP endpoints here).
Dense embedding via app.core.embeddings (local Ollama bge-m3 or Gemini); sparse via BM42
(app.ingestion.sparse). Both prefetch lists are fused with Reciprocal Rank Fusion (RRF)
inside Qdrant. Top-K defaults to 20.
Returns raw ScoredPoint list; callers are responsible for formatting.

Note: the `payload_filter` parameter is named to avoid shadowing the Python built-in `filter`.
"""

from typing import Optional

from qdrant_client.models import Filter, Fusion, FusionQuery, Prefetch, ScoredPoint

from app.core.config import get_settings
from app.core.embeddings import generate_dense_embeddings
from app.db.qdrant import COLLECTION_NAME, DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, get_qdrant_client
from app.ingestion.sparse import encode_sparse


async def hybrid_search(
    query: str,
    top_k: int = 20,
    score_threshold: float = 0.0,
    payload_filter: Optional[Filter] = None,
    embedding_provider: str = "local",
    embedding_model: str = "bge-m3",
) -> list[ScoredPoint]:
    """
    Perform a hybrid dense+sparse search with RRF fusion.

    Args:
        query: The search query string.
        top_k: Maximum number of results to return (1–100).
        score_threshold: Minimum score; 0.0 means no filtering.
        payload_filter: Optional Qdrant payload filter to apply.
        embedding_provider: Dense embedding provider ("local" or "gemini").
        embedding_model: Dense embedding model name.

    Returns:
        List of ScoredPoint objects ordered by RRF score (descending).
    """
    settings = get_settings()

    # ------------------------------------------------------------------ #
    # 1. Dense embedding                                                  #
    # ------------------------------------------------------------------ #
    dense_vectors = await generate_dense_embeddings([query], embedding_provider, embedding_model, settings)
    dense_vector = dense_vectors[0]

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


# ------------------------------------------------------------------ #
# Parent-Child context expansion                                      #
# Purpose : Expand retrieved child chunks to their parent text and   #
#           deduplicate by parent_id, keeping the highest-scoring    #
#           representative when multiple children share a parent.    #
# Note    : Pure synchronous function — no I/O.                      #
# ------------------------------------------------------------------ #

def expand_to_parents(points: list[ScoredPoint]) -> list[dict]:
    """
    Expand a list of retrieved child ScoredPoints to their parent context.

    For each point the parent_text is taken from the payload (falling back
    to text_preview when parent_text is absent). Points that share the same
    parent_id are deduplicated: only the entry with the highest score is
    kept. The returned list preserves descending-score order.

    Args:
        points: ScoredPoint list returned by hybrid_search / rerank.

    Returns:
        List of dicts with keys: parent_id, parent_text, doc_id,
        source, page_number, score.
    """
    # best score seen per parent_id → dict entry
    seen: dict[str, dict] = {}

    for point in points:
        payload = point.payload or {}
        parent_id: str = payload.get("parent_id") or str(point.id)
        parent_text: str = payload.get("parent_text") or payload.get("text_preview", "")

        # Skip points whose text could not be resolved — an empty context
        # block has no value for the LLM and would fail schema validation.
        if not parent_text.strip():
            continue

        entry = {
            "parent_id": parent_id,
            "parent_text": parent_text,
            "doc_id": payload.get("doc_id", ""),
            "source": payload.get("source", ""),
            "display_name": payload.get("display_name", ""),
            # Explicit int cast: Qdrant may round-trip numeric payload fields
            # as float (e.g. 1.0) depending on JSON serialisation path.
            "page_number": int(payload.get("page_number") or 0),
            "score": point.score,
        }

        if parent_id not in seen or point.score > seen[parent_id]["score"]:
            seen[parent_id] = entry

    return sorted(seen.values(), key=lambda e: e["score"], reverse=True)
