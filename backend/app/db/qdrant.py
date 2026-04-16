from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import get_settings

settings = get_settings()

COLLECTION_NAME = "propesqi_docs"
VECTOR_SIZE = 1024

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
    return _client


async def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    client = get_qdrant_client()
    existing = await client.get_collections()
    names = {c.name for c in existing.collections}
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
