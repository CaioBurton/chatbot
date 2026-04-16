import hashlib
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.postgres import get_db
from app.ingestion.processor import process_document
from app.models.document import Document
from app.schemas.document import DocumentListItem, DocumentUploadResponse

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
