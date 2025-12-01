"""
Health check router
Provides service health status and GPU detection
"""

from fastapi import APIRouter
from typing import Dict, Any
import logging

from ..models.ocr_engine import OCREngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint
    Returns service status and GPU availability
    """
    try:
        engine = OCREngine()
        gpu_available = engine.check_gpu_available()

        return {
            "status": "ok",
            "service": "ocr-service",
            "gpu_available": gpu_available,
            "gpu_enabled": engine.use_gpu
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "service": "ocr-service",
            "error": str(e)
        }




