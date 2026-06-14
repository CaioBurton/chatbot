"""
core/embeddings.py — Provider-agnostic dense embedding generation.

Supports:
  - "local"  — Ollama /api/embed (default model "bge-m3", 1024-dim)
  - "gemini" — Google Gemini batchEmbedContents API, with output_dimensionality
               pinned to 1024 so vectors stay compatible with the existing
               Qdrant "dense" vector (size 1024, COSINE). Qdrant's COSINE
               distance re-normalizes vectors internally, so Gemini's
               MRL-truncated (non-pre-normalized) 1024-dim output still
               ranks correctly.
"""

import httpx

# Batch size for both providers' embedding calls — keeps individual HTTP
# requests bounded regardless of how many texts the caller passes in.
_EMBED_BATCH_SIZE = 32

_GEMINI_OUTPUT_DIMENSIONALITY = 1024


async def _ollama_embed_batch(client: httpx.AsyncClient, texts: list[str], model: str, settings) -> list[list[float]]:
    response = await client.post(
        f"{settings.OLLAMA_BASE_URL}/api/embed",
        json={"model": model, "input": texts},
        timeout=300.0,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return data["embeddings"]
    except KeyError as exc:
        raise RuntimeError(f"Unexpected Ollama /api/embed response structure: {data}") from exc


async def _gemini_embed_batch(client: httpx.AsyncClient, texts: list[str], model: str, settings) -> list[list[float]]:
    response = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
        params={"key": settings.GOOGLE_API_KEY},
        json={
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": text}]},
                    "output_dimensionality": _GEMINI_OUTPUT_DIMENSIONALITY,
                }
                for text in texts
            ]
        },
        timeout=300.0,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return [item["values"] for item in data["embeddings"]]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Gemini batchEmbedContents response structure: {data}") from exc


async def generate_dense_embeddings(texts: list[str], provider: str, model: str, settings) -> list[list[float]]:
    """
    Generate dense embedding vectors for *texts* using the configured provider.

    Args:
        texts: Input strings to embed.
        provider: "local" (Ollama) or "gemini" (Google Gemini).
        model: Embedding model name (e.g. "bge-m3" or "gemini-embedding-001").
        settings: App settings (for OLLAMA_BASE_URL / GOOGLE_API_KEY).

    Returns:
        One embedding vector per input text, in the same order.
    """
    embeddings: list[list[float]] = []
    async with httpx.AsyncClient() as client:
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i : i + _EMBED_BATCH_SIZE]
            if provider == "gemini":
                batch_embeddings = await _gemini_embed_batch(client, batch, model, settings)
            else:
                batch_embeddings = await _ollama_embed_batch(client, batch, model, settings)
            embeddings.extend(batch_embeddings)
    return embeddings
