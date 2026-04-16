# =============================================================================
# PROPESQI Backend — Python 3.11 + FastAPI
# =============================================================================
# System dependencies installed:
#   - tesseract-ocr + tesseract-ocr-por : OCR engine with PT-BR language pack
#   - libgl1 + libglib2.0-0             : OpenCV runtime shared libraries
#   - poppler-utils                     : pdf2image (pdfinfo, pdftoppm, etc.)
#   - unoconv + libreoffice-writer      : ODT/DOC → text conversion
#   - curl                              : used by the Docker healthcheck
# =============================================================================

FROM python:3.11-slim AS base

# ---- System dependencies -------------------------------------------------- #
# Combine apt operations in a single layer and clean up to minimise image size.
RUN apt-get update && apt-get install -y --no-install-recommends \
        # Tesseract 5 OCR engine with Portuguese language data
        tesseract-ocr \
        tesseract-ocr-por \
        # OpenCV runtime libraries (cv2 import requires these)
        libgl1 \
        libglib2.0-0 \
        # pdf2image depends on Poppler utilities (pdftoppm, pdfinfo)
        poppler-utils \
        # unoconv: Python bridge to LibreOffice for ODT/DOC conversion
        # libreoffice-writer provides the headless conversion backend
        unoconv \
        libreoffice-writer \
        # curl is needed for the Docker Compose healthcheck on /health
        curl \
    && rm -rf /var/lib/apt/lists/*

# ---- Non-root user -------------------------------------------------------- #
# Running as a non-root user reduces the blast radius of any RCE vulnerability.
# UID 1001 avoids colliding with common system UIDs.
RUN useradd --create-home --uid 1001 --shell /bin/bash appuser

# ---- Working directory ----------------------------------------------------- #
WORKDIR /app

# ---- Python dependencies (layer-cache optimised) -------------------------- #
# Copy only requirements.txt first so this layer is rebuilt only when
# dependencies change, not on every source-code change.
COPY --chown=appuser:appuser requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- Application source --------------------------------------------------- #
COPY --chown=appuser:appuser . .

# ---- Runtime user --------------------------------------------------------- #
USER appuser

# Ensure unoconv and LibreOffice write their runtime files to the user's home
ENV HOME=/home/appuser

EXPOSE 8000

# Use exec form to receive OS signals correctly (graceful shutdown)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
