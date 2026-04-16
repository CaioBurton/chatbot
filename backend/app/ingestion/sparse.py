"""
ingestion/sparse.py — Sparse (BM42) encoder for hybrid retrieval.

New file. Uses fastembed.SparseTextEmbedding with the Qdrant/bm42-all-minilm-l6-v2-attentions
model (CPU-only, ~100 MB download on first use). The encoder instance is lazily initialised
and cached at module level behind an asyncio.Lock to prevent duplicate downloads under
concurrent startup requests. CPU-bound encoding is offloaded to a thread-pool executor so
the event loop is never blocked.
"""

import asyncio
from typing import Optional

from fastembed import SparseTextEmbedding
from qdrant_client.models import SparseVector

_MODEL_NAME = "Qdrant/bm42-all-minilm-l6-v2-attentions"

_encoder: Optional[SparseTextEmbedding] = None
_encoder_lock = asyncio.Lock()


async def get_sparse_encoder() -> SparseTextEmbedding:
    """Return the cached sparse encoder, initialising it on first call."""
    global _encoder
    async with _encoder_lock:
        if _encoder is None:
            loop = asyncio.get_running_loop()
            _encoder = await loop.run_in_executor(
                None, lambda: SparseTextEmbedding(model_name=_MODEL_NAME)
            )
    return _encoder


async def encode_sparse(texts: list[str]) -> list[SparseVector]:
    """
    Encode *texts* into sparse BM42 vectors suitable for Qdrant upsert.

    CPU-bound work runs in a thread-pool executor; returns one SparseVector per input text.
    """
    encoder = await get_sparse_encoder()
    loop = asyncio.get_running_loop()

    def _encode() -> list[SparseVector]:
        results: list[SparseVector] = []
        for embedding in encoder.embed(texts):
            results.append(
                SparseVector(
                    indices=embedding.indices.tolist(),
                    values=embedding.values.tolist(),
                )
            )
        return results

    return await loop.run_in_executor(None, _encode)
