"""
OCR processing router
Handles image and PDF OCR requests
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pathlib import Path
import tempfile
import os

from ..models.ocr_engine import OCREngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ocr", tags=["ocr"])

# Global OCR engine instance
_ocr_engine: Optional[OCREngine] = None


def get_ocr_engine() -> OCREngine:
    """Get or create OCR engine instance"""
    global _ocr_engine
    if _ocr_engine is None:
        use_gpu_env = os.getenv("OCR_USE_GPU", "").lower()
        if use_gpu_env == "true":
            use_gpu = True
        elif use_gpu_env == "false":
            use_gpu = False
        else:
            use_gpu = None
        lang = os.getenv("OCR_LANG", "ch")
        _ocr_engine = OCREngine(use_gpu=use_gpu, lang=lang)
    return _ocr_engine


@router.post("/image")
async def ocr_image(
    file: UploadFile = File(..., description="Image file to process")
) -> Dict[str, Any]:
    """
    Process single image file with OCR

    Args:
        file: Uploaded image file

    Returns:
        OCR result with text, blocks, and confidence scores
    """
    try:
        # Validate file type
        allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/tiff", "image/bmp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Allowed: {allowed_types}"
            )

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            engine = get_ocr_engine()
            result = engine.process_image(tmp_path)
            return result
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        logger.error(f"Image OCR processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


@router.post("/pdf")
async def ocr_pdf(
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = Form(300, description="DPI for PDF to image conversion")
) -> Dict[str, Any]:
    """
    Process PDF file with OCR

    Args:
        file: Uploaded PDF file
        dpi: DPI for PDF to image conversion (default: 300)

    Returns:
        OCR result with pages array containing text and blocks for each page
    """
    try:
        # Validate file type
        if file.content_type != "application/pdf":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Expected: application/pdf"
            )

        # Validate DPI
        if dpi < 150 or dpi > 600:
            raise HTTPException(
                status_code=400,
                detail="DPI must be between 150 and 600"
            )

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            engine = get_ocr_engine()
            result = engine.process_pdf(tmp_path, dpi=dpi)
            return result
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        logger.error(f"PDF OCR processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


@router.post("/image/path")
async def ocr_image_from_path(
    file_path: str = Form(..., description="Local file path to image")
) -> Dict[str, Any]:
    """
    Process image from local file path
    For local tool integration

    Args:
        file_path: Local file path to image

    Returns:
        OCR result with text, blocks, and confidence scores
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")

        engine = get_ocr_engine()
        result = engine.process_image(str(path))
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image OCR processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


@router.post("/pdf/path")
async def ocr_pdf_from_path(
    file_path: str = Form(..., description="Local file path to PDF"),
    dpi: int = Form(300, description="DPI for PDF to image conversion")
) -> Dict[str, Any]:
    """
    Process PDF from local file path
    For local tool integration

    Args:
        file_path: Local file path to PDF
        dpi: DPI for PDF to image conversion (default: 300)

    Returns:
        OCR result with pages array
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"Path is not a file: {file_path}")

        if dpi < 150 or dpi > 600:
            raise HTTPException(
                status_code=400,
                detail="DPI must be between 150 and 600"
            )

        engine = get_ocr_engine()
        result = engine.process_pdf(str(path), dpi=dpi)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF OCR processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")




