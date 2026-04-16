import asyncio
from typing import Any


def _sync_extract(file_path: str) -> list[dict[str, Any]]:
    """Run pdfplumber extraction synchronously (called in executor)."""
    import pdfplumber

    pages: list[dict[str, Any]] = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page_number": i, "text": text})
    return pages


async def extract_pdf(file_path: str) -> tuple[list[dict[str, Any]], bool]:
    """
    Extract text from a native PDF page by page.

    Returns:
        (pages, is_scanned) where pages is a list of {"page_number": int, "text": str}
        and is_scanned is True when the average chars/page < 50, indicating the PDF
        likely requires OCR rather than native text extraction.
    """
    loop = asyncio.get_running_loop()
    pages: list[dict[str, Any]] = await loop.run_in_executor(
        None, _sync_extract, file_path
    )

    if not pages:
        return pages, True  # empty PDF — treat as scanned

    total_chars = sum(len(p["text"]) for p in pages)
    avg_chars = total_chars / len(pages)
    is_scanned = avg_chars < 50

    return pages, is_scanned
