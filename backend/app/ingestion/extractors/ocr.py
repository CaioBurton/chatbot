import asyncio
import math
from typing import Any

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path

# Maximum plausible skew angle for a text document.
# Beyond this the moment estimate is unreliable (e.g. pages with large
# filled shapes or solid borders) and rotation would destroy readability.
_MAX_DESKEW_ANGLE_DEG: float = 45.0


def _deskew(image: np.ndarray) -> np.ndarray:
    """
    Deskew a binary image using image moments.

    Computes the skew angle from the second-order central moments and applies
    an affine rotation.  Skips rotation when |angle| < 0.5° to avoid
    introducing interpolation artefacts on already-straight pages.
    """
    moments = cv2.moments(image, binaryImage=True)
    mu11 = moments["mu11"]
    mu20 = moments["mu20"]
    mu02 = moments["mu02"]

    # Guard against blank / near-blank pages where moments are ~0
    if abs(mu20 - mu02) < 1e-6 and abs(mu11) < 1e-6:
        return image

    angle_rad = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
    angle_deg = math.degrees(angle_rad)

    # Skip trivial rotations; clamp extreme angles that indicate a bad
    # moment estimate rather than real skew.
    if abs(angle_deg) < 0.5 or abs(angle_deg) > _MAX_DESKEW_ANGLE_DEG:
        return image

    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rotated = cv2.warpAffine(
        image,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def _preprocess_and_ocr(pil_image: Any) -> str:
    """
    Preprocess a single PIL image and run Tesseract OCR.

    Normalises the PIL mode to RGB first so that cv2 colour conversion
    never receives an unexpected number of channels (e.g. RGBA from a PDF
    with transparency, or CMYK / P / L from non-standard renderings).

    Preprocessing pipeline (applied in order):
        1. Normalise to RGB (handles RGBA, CMYK, L, P, …)
        2. RGB → grayscale
        3. Gaussian denoise  (3×3 kernel)
        4. Otsu binarization (THRESH_BINARY + THRESH_OTSU)
        5. Deskew via image moments (skipped when |angle| < 0.5° or > 45°)
    """
    # Normalise to RGB regardless of source mode — prevents channel-count
    # mismatches inside cv2.cvtColor when pdf2image returns RGBA, CMYK, etc.
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    img = np.array(pil_image)

    # Step 1: Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Step 2: Gaussian denoise (3×3 kernel, σ determined automatically)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)

    # Step 3: Otsu binarization
    _, binary = cv2.threshold(
        denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # Step 4: Deskew
    deskewed = _deskew(binary)

    # OCR — Portuguese language pack, PSM 1 (auto page segmentation + OSD),
    # OEM 3 (LSTM engine only, best accuracy for modern Tesseract builds)
    return pytesseract.image_to_string(
        deskewed,
        lang="por",
        config="--psm 1 --oem 3",
    )


def _sync_extract_ocr(file_path: str) -> list[dict[str, Any]]:
    """
    Render each PDF page to a PIL image at 300 DPI, apply OpenCV preprocessing,
    then run Tesseract OCR.  Called inside a thread-pool executor.

    Pages are rendered one at a time (first_page / last_page) so memory usage
    is O(1 page) instead of O(total pages).  Without this, a large scanned PDF
    at 300 DPI could exhaust container memory.
    """
    info = pdfinfo_from_path(file_path)
    total_pages: int = info.get("Pages", 0)
    pages: list[dict[str, Any]] = []

    for page_num in range(1, total_pages + 1):
        pil_images = convert_from_path(
            file_path, dpi=300, first_page=page_num, last_page=page_num
        )
        if not pil_images:
            # Renderer returned nothing for this page — record empty text so
            # page numbering stays contiguous.
            pages.append({"page_number": page_num, "text": ""})
            continue

        text = _preprocess_and_ocr(pil_images[0])
        pages.append({"page_number": page_num, "text": text})

    return pages


async def extract_pdf_ocr(file_path: str) -> list[dict[str, Any]]:
    """
    Extract text from a scanned PDF using OCR, page by page.

    Each page is rendered at 300 DPI, preprocessed (grayscale → denoise →
    binarise → deskew), then passed to Tesseract with the Portuguese language
    pack.  CPU-bound work is offloaded to the default thread-pool executor so
    the event loop is not blocked.

    Returns:
        List of {"page_number": int, "text": str} dicts, one per page.
        Same schema as extract_pdf() in extractors/pdf.py.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_extract_ocr, file_path)
