"""
db/qdrant.py — Qdrant client singleton and collection management.

Changed: ensure_collection() now creates a named-vector collection
  {"dense": VectorParams} + sparse_vectors_config {"sparse": SparseVectorParams(IDF)}.
  Upgrade path: if the collection exists with an incompatible (old single-vector)
  config it is deleted and recreated; a valid named-vector collection is left untouched.
  DENSE_VECTOR_NAME / SPARSE_VECTOR_NAME constants are exported for use by
  processor.py and search.py.
"""

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, Modifier, SparseVectorParams, VectorParams

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

COLLECTION_NAME = "propesqi_docs"
VECTOR_SIZE = 1024
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
    return _client


async def _is_collection_compatible(client: AsyncQdrantClient) -> bool:
    """
    Return True only if the collection already has the expected named-vector config.

    Intentionally does NOT catch exceptions — a transient Qdrant error should
    propagate and abort ensure_collection() rather than silently returning False
    and triggering a destructive delete.
    """
    info = await client.get_collection(COLLECTION_NAME)
    vectors = info.config.params.vectors
    sparse = info.config.params.sparse_vectors
    return (
        isinstance(vectors, dict)
        and DENSE_VECTOR_NAME in vectors
        and getattr(vectors[DENSE_VECTOR_NAME], "size", None) == VECTOR_SIZE
        and sparse is not None
        and SPARSE_VECTOR_NAME in sparse
    )


async def ensure_collection() -> None:
    """
    Create the Qdrant collection with named dense + sparse vectors.

    - Fresh install: collection does not exist → create it.
    - Upgrade path: collection exists with old single-vector config → delete and recreate.
    - Already valid: collection has the expected named-vector config → no-op.
    """
    client = get_qdrant_client()
    existing = await client.get_collections()
    names = {c.name for c in existing.collections}

    if COLLECTION_NAME in names:
        if await _is_collection_compatible(client):
            return  # already configured correctly — leave it untouched
        # Incompatible config (e.g. old unnamed single-vector collection); must recreate.
        logger.warning(
            "Collection '%s' exists with incompatible vector config. "
            "Deleting and recreating — all previously indexed data will be lost.",
            COLLECTION_NAME,
        )
        await client.delete_collection(COLLECTION_NAME)

    await client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(modifier=Modifier.IDF)
        },
    )
