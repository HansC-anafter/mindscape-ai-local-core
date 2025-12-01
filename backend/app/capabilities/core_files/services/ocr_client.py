"""
OCR Service Client
Client for communicating with local OCR service
"""

import logging
import os
from typing import Dict, Any, Optional
import httpx
from pathlib import Path

logger = logging.getLogger(__name__)


class OCRClient:
    """
    Client for OCR service
    Handles communication with local PaddleOCR service
    """

    def __init__(self, service_url: Optional[str] = None):
        """
        Initialize OCR client

        Args:
            service_url: OCR service URL (default: from environment)
        """
        self.service_url = service_url or os.getenv(
            "OCR_SERVICE_URL",
            "http://ocr-service:8001"
        )
        self.timeout = 300.0  # 5 minutes for large PDFs

    async def ocr_image(self, file_path: str) -> Dict[str, Any]:
        """
        Process image file with OCR

        Args:
            file_path: Path to image file

        Returns:
            OCR result with text, blocks, and confidence scores
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(file_path, "rb") as f:
                    files = {"file": (path.name, f, "image/png")}
                    response = await client.post(
                        f"{self.service_url}/ocr/image/path",
                        data={"file_path": str(path)},
                        timeout=self.timeout
                    )
                    response.raise_for_status()
                    return response.json()

        except httpx.HTTPError as e:
            logger.error(f"OCR service request failed: {e}")
            raise Exception(f"OCR service unavailable: {str(e)}")
        except Exception as e:
            logger.error(f"Image OCR processing failed: {e}")
            raise

    async def ocr_pdf(self, file_path: str, dpi: int = 300) -> Dict[str, Any]:
        """
        Process PDF file with OCR

        Args:
            file_path: Path to PDF file
            dpi: DPI for PDF to image conversion (default: 300)

        Returns:
            OCR result with pages array
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.service_url}/ocr/pdf/path",
                    data={
                        "file_path": str(path),
                        "dpi": dpi
                    },
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"OCR service request failed: {e}")
            raise Exception(f"OCR service unavailable: {str(e)}")
        except Exception as e:
            logger.error(f"PDF OCR processing failed: {e}")
            raise

    async def check_health(self) -> Dict[str, Any]:
        """
        Check OCR service health

        Returns:
            Health status including GPU availability
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.service_url}/health")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.warning(f"OCR service health check failed: {e}")
            return {"status": "unavailable", "error": str(e)}


# Global OCR client instance
_ocr_client: Optional[OCRClient] = None


def get_ocr_client() -> OCRClient:
    """Get or create OCR client instance"""
    global _ocr_client
    if _ocr_client is None:
        _ocr_client = OCRClient()
    return _ocr_client


# Tool functions for manifest.yaml
async def ocr_image(file_path: str) -> Dict[str, Any]:
    """
    Extract text from image using OCR service
    Tool function for manifest.yaml

    Args:
        file_path: Path to image file

    Returns:
        OCR result with text, blocks, and confidence scores
    """
    client = get_ocr_client()
    return await client.ocr_image(file_path)


async def ocr_pdf(file_path: str, dpi: int = 300) -> Dict[str, Any]:
    """
    Extract text from PDF using OCR service
    Tool function for manifest.yaml

    Args:
        file_path: Path to PDF file
        dpi: DPI for PDF to image conversion (default: 300)

    Returns:
        OCR result with pages array
    """
    client = get_ocr_client()
    return await client.ocr_pdf(file_path, dpi=dpi)






