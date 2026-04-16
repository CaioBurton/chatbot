import hashlib
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, UploadFile, status
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.postgres import get_db
from app.db.qdrant import COLLECTION_NAME, get_qdrant_client
from app.db.search import hybrid_search
from app.ingestion.processor import process_document
from app.models.document import Document
from app.schemas.document import (
    DocumentDetail,
    DocumentListItem,
    DocumentUploadResponse,
    HybridSearchRequest,
    SearchResultItem,
)

router = APIRouter(prefix="/documents", tags=["documents"])

_UPLOAD_DIR = Path("/app/uploads")
_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
_PDF_MAGIC = b"%PDF"

logger = logging.getLogger(__name__)


def _sanitise_filename(raw: str) -> str:
    """
    Strip null bytes and path components, replace non-alphanumeric chars
    (except . and -) with underscores, and cap at 200 characters.
    """
    raw = raw.replace("\x00", "")        # strip null bytes (CWE-626)
    name = Path(raw).name               # drop any path prefix (prevents path traversal)
    name = re.sub(r"[^a-zA-Z0-9.\-]", "_", name)
    return name[:200] or "upload.pdf"


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentUploadResponse,
)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> DocumentUploadResponse:
    # ------------------------------------------------------------------ #
    # 1. MIME allowlist — only application/pdf accepted
    # ------------------------------------------------------------------ #
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only application/pdf files are accepted",
        )

    # ------------------------------------------------------------------ #
    # 2. Read bytes and enforce size limit
    # ------------------------------------------------------------------ #
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 50 MB size limit",
        )

    # ------------------------------------------------------------------ #
    # 2b. Magic bytes check — verify actual file content, not just the
    #     client-supplied Content-Type header (OWASP A03 / CWE-351).
    # ------------------------------------------------------------------ #
    if not content.startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File content is not a valid PDF",
        )

    # ------------------------------------------------------------------ #
    # 3. Sanitise filename (path traversal prevention)
    # ------------------------------------------------------------------ #
    sanitised_name = _sanitise_filename(file.filename or "upload.pdf")

    # ------------------------------------------------------------------ #
    # 4. Deduplication via SHA-256
    # ------------------------------------------------------------------ #
    file_hash = hashlib.sha256(content).hexdigest()
    result = await db.execute(
        select(Document).where(Document.file_hash == file_hash)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Duplicate file already exists", "id": str(existing.id)},
        )

    # ------------------------------------------------------------------ #
    # 5. Persist file to disk
    # ------------------------------------------------------------------ #
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_filename = f"{uuid.uuid4()}_{sanitised_name}"
    file_path = _UPLOAD_DIR / storage_filename
    file_path.write_bytes(content)

    # ------------------------------------------------------------------ #
    # 6. Insert document record (status=uploaded)
    #    If this fails, delete the orphaned file so disk and DB stay in sync.
    # ------------------------------------------------------------------ #
    doc = Document(
        filename=storage_filename,
        original_name=file.filename or sanitised_name,
        file_hash=file_hash,
        file_type="pdf_native",
        ocr_applied=False,
        status="uploaded",
    )
    try:
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    # ------------------------------------------------------------------ #
    # 7. Schedule background ingestion
    # ------------------------------------------------------------------ #
    background_tasks.add_task(
        process_document,
        str(doc.id),
        str(file_path),
        file.filename or sanitised_name,
    )

    return DocumentUploadResponse(
        id=doc.id,
        status=doc.status,
        original_name=doc.original_name,
    )


@router.get("", response_model=list[DocumentListItem])
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> list[DocumentListItem]:
    result = await db.execute(
        select(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()
    return [DocumentListItem.model_validate(doc) for doc in docs]


# ------------------------------------------------------------------ #
# GET /documents/{doc_id}                                              #
# Purpose : Return full metadata for a single document.               #
# Auth    : require_admin (JWT, role admin or superadmin)              #
# Status  : 200 OK | 404 Not Found                                    #
# ------------------------------------------------------------------ #
@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> DocumentDetail:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentDetail.model_validate(doc)


# ------------------------------------------------------------------ #
# DELETE /documents/{doc_id}                                          #
# Purpose : Remove a document from PostgreSQL, Qdrant, and disk.      #
# Auth    : require_admin (JWT, role admin or superadmin)              #
# Status  : 204 No Content | 404 Not Found                            #
# ------------------------------------------------------------------ #
@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> Response:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # ------------------------------------------------------------------ #
    # 1. Delete the database record first (authoritative).               #
    #    Committing here keeps the DB as the source of truth: if Qdrant  #
    #    or file cleanup fail afterwards the document is already gone    #
    #    from the user's view; orphaned data becomes a maintenance task, #
    #    not a user-facing inconsistency.                                #
    # ------------------------------------------------------------------ #
    filename = doc.filename  # capture before session expiry
    await db.delete(doc)
    await db.commit()

    # ------------------------------------------------------------------ #
    # 2. Delete Qdrant points by payload filter so orphaned points are   #
    #    also cleaned up even if their UUID was regenerated.             #
    # ------------------------------------------------------------------ #
    qdrant = get_qdrant_client()
    await qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="doc_id",
                        match=MatchValue(value=str(doc_id)),
                    )
                ]
            )
        ),
    )

    # ------------------------------------------------------------------ #
    # 3. Delete physical file (missing file is not fatal)                #
    # ------------------------------------------------------------------ #
    (_UPLOAD_DIR / filename).unlink(missing_ok=True)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ #
# POST /documents/{doc_id}/reindex                                    #
# Purpose : Re-trigger ingestion for a document in error/uploaded     #
#           state. Resets status and schedules background processing. #
# Auth    : require_admin (JWT, role admin or superadmin)             #
# Status  : 202 Accepted | 404 Not Found | 409 Conflict               #
# ------------------------------------------------------------------ #
@router.post(
    "/{doc_id}/reindex",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentUploadResponse,
)
async def reindex_document(
    doc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
) -> DocumentUploadResponse:
    # .with_for_update() acquires a row-level lock so concurrent reindex
    # requests on the same document cannot both pass the status guard and
    # schedule duplicate background tasks.
    result = await db.execute(
        select(Document).where(Document.id == doc_id).with_for_update()
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # ------------------------------------------------------------------ #
    # 1. Only allow reindex when the document is in a retriable state    #
    # ------------------------------------------------------------------ #
    if doc.status not in ("error", "uploaded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is already active or processing; reindex not permitted",
        )

    # ------------------------------------------------------------------ #
    # 2. Verify the physical file still exists on disk                   #
    # ------------------------------------------------------------------ #
    file_path = _UPLOAD_DIR / doc.filename
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file no longer exists on disk; upload the document again",
        )

    # ------------------------------------------------------------------ #
    # 3. Reset document state and persist                                #
    # ------------------------------------------------------------------ #
    doc.status = "uploaded"
    doc.error_message = None
    await db.commit()

    # ------------------------------------------------------------------ #
    # 4. Schedule background re-ingestion                                #
    # ------------------------------------------------------------------ #
    background_tasks.add_task(
        process_document,
        str(doc.id),
        str(file_path),
        doc.original_name,
    )

    return DocumentUploadResponse(
        id=doc.id,
        status=doc.status,
        original_name=doc.original_name,
    )


# ------------------------------------------------------------------ #
# POST /documents/search                                              #
# Purpose : Hybrid dense+sparse search with RRF fusion (Top-K=20).   #
# Auth    : require_admin (JWT, role admin or superadmin)             #
# Status  : 200 OK                                                    #
# Note    : All input validation is enforced by Pydantic before this  #
#           handler runs, regardless of the frontend.                 #
# ------------------------------------------------------------------ #
@router.post("/search", response_model=list[SearchResultItem])
async def search_documents(
    body: HybridSearchRequest,
    _user=Depends(require_admin),
) -> list[SearchResultItem]:
    points = await hybrid_search(
        query=body.query,
        top_k=body.top_k,
        score_threshold=body.score_threshold,
    )
    return [
        SearchResultItem(
            chunk_id=str(point.id),
            score=point.score,
            doc_id=point.payload.get("doc_id", ""),
            source=point.payload.get("source", ""),
            page_number=point.payload.get("page_number", 0),
            text_preview=point.payload.get("text_preview", ""),
            chunk_index=point.payload.get("chunk_index", 0),
        )
        for point in points
    ]
