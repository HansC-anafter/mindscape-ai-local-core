"""
Core Files: PDF/DOCX Text Extraction Service
Extract text from PDF/DOCX files with automatic OCR for scanned PDFs
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from ....shared.file_utils import (
    pdf_to_text,
    docx_to_text,
    detect_file_type,
    pdf_has_text_layer
)
from .ocr_client import get_ocr_client

logger = logging.getLogger(__name__)


async def extract_text(
    file_path: str,
    file_type: Optional[str] = None,
    use_ocr: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Extract text from PDF/DOCX file
    Automatically detects scanned PDFs and uses OCR if needed

    Args:
        file_path: File path
        file_type: File type ('pdf', 'docx', 'doc'), auto-detect if None
        use_ocr: Force OCR usage (None = auto-detect, True = force OCR, False = skip OCR)

    Returns:
        Dict containing:
            - text: Extracted text content
            - metadata: Information including page_count/paragraph_count, word_count, etc.
            - ocr_used: Boolean indicating if OCR was used
            - quality: OCR quality metrics (if OCR was used)
    """
    try:
        # Check if file exists
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Auto-detect file type if not specified
        if not file_type:
            file_type = detect_file_type(file_path)

        # Extract text based on file type
        if file_type == 'pdf':
            # Check if PDF has text layer
            has_text = pdf_has_text_layer(file_path)

            # Decision logic: use OCR if no text layer or forced
            if use_ocr is True or (use_ocr is None and not has_text):
                logger.info(f"PDF appears to be scanned, using OCR: {file_path}")
                try:
                    ocr_client = get_ocr_client()
                    # Check OCR service health first
                    health = await ocr_client.check_health()
                    if health.get("status") != "ok":
                        logger.warning(f"OCR service unavailable: {health.get('error', 'unknown')}, falling back to standard extraction")
                        # Fallback to standard extraction even if no text layer
                        result = pdf_to_text(file_path)
                        result["ocr_used"] = False
                        result["ocr_fallback"] = True
                        result["ocr_error"] = health.get("error", "OCR service unavailable")
                        return result

                    ocr_result = await ocr_client.ocr_pdf(file_path)
                except Exception as ocr_error:
                    logger.error(f"OCR processing failed: {ocr_error}, falling back to standard extraction")
                    # Fallback to standard extraction on OCR error
                    result = pdf_to_text(file_path)
                    result["ocr_used"] = False
                    result["ocr_fallback"] = True
                    result["ocr_error"] = str(ocr_error)
                    return result

                # Convert OCR result to standard format
                text_parts = []
                all_blocks = []
                total_confidence = 0.0
                confidence_count = 0

                for page in ocr_result.get("pages", []):
                    text_parts.append(page.get("text", ""))
                    blocks = page.get("blocks", [])
                    all_blocks.extend(blocks)

                    # Calculate average confidence
                    for block in blocks:
                        conf = block.get("confidence", 0.0)
                        total_confidence += conf
                        confidence_count += 1

                full_text = "\n\n".join(text_parts)
                avg_confidence = total_confidence / confidence_count if confidence_count > 0 else 0.0

                return {
                    "text": full_text,
                    "metadata": {
                        "page_count": ocr_result.get("total_pages", 0),
                        "word_count": len(full_text.split()),
                        "file_path": file_path,
                        "ocr_used": True
                    },
                    "ocr_used": True,
                    "quality": {
                        "average_confidence": avg_confidence,
                        "total_blocks": len(all_blocks),
                        "low_confidence_blocks": len([b for b in all_blocks if b.get("confidence", 0) < 0.90])
                    }
                }
            else:
                # Use standard PDF text extraction
                result = pdf_to_text(file_path)
                result["ocr_used"] = False
                return result

        elif file_type in ['docx', 'doc']:
            result = docx_to_text(file_path)
            result["ocr_used"] = False
            return result
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    except Exception as e:
        logger.error(f"Text extraction failed for {file_path}: {e}")
        raise
