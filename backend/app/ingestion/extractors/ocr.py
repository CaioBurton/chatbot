"""
extractors/ocr.py — OCR for scanned PDFs via the LLMWhisperer cloud API.

Replaces the previous local pipeline (pdf2image + OpenCV preprocessing +
Tesseract) so no OCR model/binary runs on the app server. Submits the PDF to
LLMWhisperer's /whisper endpoint, polls /whisper-status until processed, then
retrieves the extracted text once (the API only allows a single retrieval per
job) and splits it on the page separator to rebuild per-page entries.
"""

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings

_PAGE_SEPARATOR = "<<<"
_POLL_INTERVAL_SECONDS = 5.0
_MAX_POLL_SECONDS = 600.0


async def _submit_whisper_job(client: httpx.AsyncClient, file_path: str, settings) -> str:
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    response = await client.post(
        f"{settings.LLMWHISPERER_BASE_URL}/whisper",
        params={
            "mode": "high_quality",
            "output_mode": "text",
            "page_separator": _PAGE_SEPARATOR,
        },
        headers={
            "unstract-key": settings.LLMWHISPERER_API_KEY,
            "Content-Type": "application/octet-stream",
        },
        content=file_bytes,
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["whisper_hash"]


async def _wait_until_processed(client: httpx.AsyncClient, whisper_hash: str, settings) -> None:
    elapsed = 0.0
    while elapsed < _MAX_POLL_SECONDS:
        response = await client.get(
            f"{settings.LLMWHISPERER_BASE_URL}/whisper-status",
            params={"whisper_hash": whisper_hash},
            headers={"unstract-key": settings.LLMWHISPERER_API_KEY},
            timeout=30.0,
        )
        response.raise_for_status()
        status = response.json()["status"]
        if status == "processed":
            return
        if status == "error":
            raise RuntimeError(f"LLMWhisperer job {whisper_hash} failed: {response.text}")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        elapsed += _POLL_INTERVAL_SECONDS
    raise TimeoutError(
        f"LLMWhisperer job {whisper_hash} did not finish within {_MAX_POLL_SECONDS:.0f}s"
    )


async def _retrieve_result(client: httpx.AsyncClient, whisper_hash: str, settings) -> dict[str, Any]:
    response = await client.get(
        f"{settings.LLMWHISPERER_BASE_URL}/whisper-retrieve",
        params={"whisper_hash": whisper_hash},
        headers={"unstract-key": settings.LLMWHISPERER_API_KEY},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


async def extract_pdf_ocr(file_path: str) -> list[dict[str, Any]]:
    """
    Extract text from a scanned PDF using the LLMWhisperer cloud OCR API.

    Returns:
        List of {"page_number": int, "text": str} dicts, one per page.
        Same schema as extract_pdf() in extractors/pdf.py.
    """
    settings = get_settings()
    if not settings.LLMWHISPERER_API_KEY:
        raise RuntimeError(
            "LLMWHISPERER_API_KEY is not configured — required to OCR scanned PDFs."
        )

    async with httpx.AsyncClient() as client:
        whisper_hash = await _submit_whisper_job(client, file_path, settings)
        await _wait_until_processed(client, whisper_hash, settings)
        result = await _retrieve_result(client, whisper_hash, settings)

    # result_text has a trailing separator + form-feed after the last page,
    # which would otherwise show up as a spurious empty extra page — trim the
    # split to the page count the API itself reports for this document.
    raw_pages = [page.strip() for page in result["result_text"].split(_PAGE_SEPARATOR)]
    total_pages = result.get("whisper_metadata", {}).get("total_page_count")
    if total_pages is not None:
        raw_pages = raw_pages[:total_pages]

    return [{"page_number": i, "text": page_text} for i, page_text in enumerate(raw_pages, start=1)]
