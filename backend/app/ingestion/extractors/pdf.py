import asyncio
from typing import Any


def _extract_metadata_title(file_path: str) -> str | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        metadata = reader.metadata or {}
        title = getattr(metadata, "title", None)
        if isinstance(title, str) and title.strip():
            return title.strip()
    except Exception:
        return None
    return None


def _sync_extract(file_path: str) -> list[dict[str, Any]]:
    """Run pdfplumber extraction synchronously (called in executor)."""
    import pdfplumber

    # x_tolerance=1 (pdfplumber default is 3): some PDFs — observed in the
    # 2026/2027 PIBIC/PIBITI/PIBIC-EM editais — use tight character spacing
    # that falls under the default gap threshold, causing extract_text() to
    # merge adjacent words ("ANEXOVI—Critériosparaavaliação..."). Verified
    # against several already-clean PDFs with no regression before lowering
    # this globally.
    pages: list[dict[str, Any]] = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1) or ""
            pages.append({"page_number": i, "text": text})
    return pages


async def extract_pdf(file_path: str) -> tuple[list[dict[str, Any]], bool, str | None]:
    """
    Extract text from a native PDF page by page.

    Returns:
        (pages, is_scanned, metadata_title) where pages is a list of
        {"page_number": int, "text": str}
        and is_scanned is True when the average chars/page < 50, indicating the PDF
        likely requires OCR rather than native text extraction.
    """
    loop = asyncio.get_running_loop()
    pages: list[dict[str, Any]] = await loop.run_in_executor(
        None, _sync_extract, file_path
    )
    metadata_title = await loop.run_in_executor(None, _extract_metadata_title, file_path)

    if not pages:
        return pages, True, metadata_title  # empty PDF — treat as scanned

    total_chars = sum(len(p["text"]) for p in pages)
    avg_chars = total_chars / len(pages)
    is_scanned = avg_chars < 50

    return pages, is_scanned, metadata_title
