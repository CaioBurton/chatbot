# ingestion/processor.py
# Changed: PointStruct now uses named vectors {"dense": ..., "sparse": ...} to match
# the updated Qdrant collection config. sparse vectors come from app.ingestion.sparse
# (BM42 via fastembed). text_preview added to Qdrant payload so hybrid search results
# can surface it without a secondary PostgreSQL lookup.

import logging
import uuid
from typing import Any

import httpx
from qdrant_client.models import PointStruct
from sqlalchemy import text, update

from app.core.config import get_settings
from app.core.progress import publish
from app.db.postgres import AsyncSessionLocal
from app.db.qdrant import COLLECTION_NAME, DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, get_qdrant_client
from app.db.rag_config import get_rag_config
from app.ingestion.chunker import chunk_pages
from app.ingestion.extractors.ocr import extract_pdf_ocr
from app.ingestion.extractors.pdf import extract_pdf
from app.ingestion.sparse import encode_sparse
from app.models.document import Document

logger = logging.getLogger(__name__)
settings = get_settings()

_EMBED_BATCH_SIZE = 32
_QDRANT_BATCH_SIZE = 100


async def _safe_publish(doc_id: str, event: dict) -> None:
    """Publish a progress event, swallowing any exception as a warning."""
    try:
        publish(doc_id, event)
    except Exception:
        logger.warning("Failed to publish progress event for doc_id=%s", doc_id)


async def _embed_batch(
    client: httpx.AsyncClient, texts: list[str]
) -> list[list[float]]:
    """
    Call Ollama /api/embed (batch endpoint) for a list of texts.
    Returns a list of dense float vectors, one per input text.
    """
    response = await client.post(
        f"{settings.OLLAMA_BASE_URL}/api/embed",
        json={"model": "bge-m3", "input": texts},
        timeout=300.0,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


async def process_document(
    document_id: str,
    file_path: str,
    original_name: str,
) -> None:
    """
    Background ingestion pipeline for a single PDF document.

    Status transitions:
        uploaded → processing → active  (success — native and scanned PDFs)
        uploaded → processing → error   (any exception, or empty document)

    This function must never raise — a crash here would silently kill the
    background task without updating the document status.
    """
    doc_uuid = uuid.UUID(document_id)

    async with AsyncSessionLocal() as db:
        try:
            # ------------------------------------------------------------------ #
            # 1. Mark as processing
            # ------------------------------------------------------------------ #
            await db.execute(
                update(Document)
                .where(Document.id == doc_uuid)
                .values(status="processing")
            )
            await db.commit()

            # ------------------------------------------------------------------ #
            # 2. Extract text from PDF
            # ------------------------------------------------------------------ #
            rag_cfg = await get_rag_config(db)
            await _safe_publish(document_id, {
                "step": "extracting",
                "detail": "Extraindo texto do PDF...",
                "progress": 10,
            })
            pages, is_scanned = await extract_pdf(file_path)

            if is_scanned:
                await _safe_publish(document_id, {
                    "step": "ocr",
                    "detail": "Aplicando OCR no documento escaneado...",
                    "progress": 20,
                })
                pages = await extract_pdf_ocr(file_path)

            # ------------------------------------------------------------------ #
            # 3. Chunk the extracted text
            # ------------------------------------------------------------------ #
            await _safe_publish(document_id, {
                "step": "chunking",
                "detail": "Fragmentando o texto em chunks...",
                "progress": 35,
            })
            # Chunk-size changes apply only to documents processed after the
            # change; existing indexed chunks are unaffected.
            chunks: list[dict[str, Any]] = await chunk_pages(
                pages,
                document_id,
                original_name,
                parent_tokens=rag_cfg.parent_chunk_tokens,
                child_tokens=rag_cfg.child_chunk_tokens,
            )

            if not chunks:
                await db.execute(
                    update(Document)
                    .where(Document.id == doc_uuid)
                    .values(
                        status="error",
                        error_message="No text content could be extracted from PDF",
                    )
                )
                await db.commit()
                await _safe_publish(document_id, {
                    "step": "error",
                    "detail": "Nenhum texto pôde ser extraído do PDF.",
                    "progress": 100,
                })
                return

            # ------------------------------------------------------------------ #
            # 4. Embed via Ollama (batched)
            # ------------------------------------------------------------------ #
            texts = [c["text"] for c in chunks]
            total_texts = len(texts)
            embeddings: list[list[float]] = []

            async with httpx.AsyncClient() as http_client:
                for i in range(0, total_texts, _EMBED_BATCH_SIZE):
                    batch = texts[i : i + _EMBED_BATCH_SIZE]
                    batch_embeddings = await _embed_batch(http_client, batch)
                    embeddings.extend(batch_embeddings)
                    batch_end = i + len(batch)
                    embed_progress = 50 + round((batch_end / total_texts) * 30)
                    await _safe_publish(document_id, {
                        "step": "embedding",
                        "detail": f"Gerando embeddings ({batch_end}/{total_texts} textos)...",
                        "progress": embed_progress,
                    })

            sparse_vectors = await encode_sparse(texts)

            if len(sparse_vectors) != len(texts):
                raise RuntimeError(
                    f"Sparse encoder returned {len(sparse_vectors)} vectors "
                    f"for {len(texts)} texts; aborting to prevent vector mismatch"
                )

            # ------------------------------------------------------------------ #
            # 5. Upsert points to Qdrant (batched)
            # ------------------------------------------------------------------ #
            await _safe_publish(document_id, {
                "step": "indexing",
                "detail": "Indexando vetores no Qdrant...",
                "progress": 85,
            })
            qdrant = get_qdrant_client()
            points = [
                PointStruct(
                    id=chunk["id"],
                    vector={
                        DENSE_VECTOR_NAME: embeddings[idx],
                        SPARSE_VECTOR_NAME: sparse_vectors[idx],
                    },
                    payload={**chunk["metadata"], "text_preview": chunk["text"][:200]},
                )
                for idx, chunk in enumerate(chunks)
            ]

            for i in range(0, len(points), _QDRANT_BATCH_SIZE):
                await qdrant.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points[i : i + _QDRANT_BATCH_SIZE],
                )

            # ------------------------------------------------------------------ #
            # 6. Mirror chunks to PostgreSQL (single executemany round-trip)
            # ------------------------------------------------------------------ #
            await _safe_publish(document_id, {
                "step": "saving",
                "detail": "Salvando chunks no banco de dados...",
                "progress": 90,
            })
            chunk_params = [
                {
                    "document_id": doc_uuid,
                    "qdrant_id": uuid.UUID(chunk["id"]),
                    "page_number": chunk["metadata"]["page_number"],
                    "chunk_index": chunk["metadata"]["chunk_index"],
                    "text_preview": chunk["text"][:200],
                }
                for chunk in chunks
            ]
            await db.execute(
                text(
                    "INSERT INTO chunks "
                    "(document_id, qdrant_id, page_number, chunk_index, text_preview) "
                    "VALUES (:document_id, :qdrant_id, :page_number, :chunk_index, :text_preview)"
                ),
                chunk_params,
            )

            # ------------------------------------------------------------------ #
            # 7. Mark document as active
            # ------------------------------------------------------------------ #
            active_values: dict[str, Any] = {"status": "active", "total_chunks": len(chunks)}
            if is_scanned:
                active_values["file_type"] = "pdf_scanned"
            await db.execute(
                update(Document)
                .where(Document.id == doc_uuid)
                .values(**active_values)
            )
            await db.commit()
            await _safe_publish(document_id, {
                "step": "done",
                "detail": "Documento indexado com sucesso.",
                "progress": 100,
            })

            logger.info(
                "Document %s indexed successfully (%d chunks)", document_id, len(chunks)
            )

        except Exception as exc:
            logger.exception(
                "Background ingestion failed for document %s", document_id
            )
            try:
                await db.rollback()
                await db.execute(
                    update(Document)
                    .where(Document.id == doc_uuid)
                    .values(
                        status="error",
                        error_message=str(exc)[:500],  # cap length; avoid storing huge traces
                        retry_count=Document.retry_count + 1,
                    )
                )
                await db.commit()
                await _safe_publish(document_id, {
                    "step": "error",
                    "detail": "Erro durante a indexação.",
                    "progress": 100,
                })
            except Exception:
                logger.exception(
                    "Failed to persist error status for document %s", document_id
                )
