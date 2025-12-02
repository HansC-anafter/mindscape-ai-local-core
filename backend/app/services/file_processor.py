"""
File Processor Service

Processes uploaded files and extracts basic information:
- File metadata (name, size, type, pages)
- Text content extraction
- Language detection
- File type detection
"""

import logging
import base64
import mimetypes
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FileProcessor:
    """Process uploaded files and extract basic information"""

    def __init__(self):
        pass

    async def process_file(
        self,
        file_data: str,
        file_name: str,
        file_type: Optional[str] = None,
        file_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process uploaded file and extract basic information

        Args:
            file_data: Base64 encoded file data or file ID
            file_name: Original file name
            file_type: MIME type (optional)
            file_size: File size in bytes (optional)

        Returns:
            Dictionary with file information
        """
        try:
            file_info = {
                "name": file_name,
                "size": file_size or 0,
                "type": file_type or self._detect_mime_type(file_name),
                "processed_at": datetime.utcnow().isoformat()
            }

            if file_data.startswith('data:'):
                file_info["format"] = "base64_data_url"
            else:
                file_info["format"] = "file_id"

            file_info["language"] = self._detect_language(file_name)
            file_info["detected_type"] = self._detect_file_type(file_name, file_info["type"])

            pages = self._estimate_pages(file_name, file_size)
            if pages:
                file_info["pages"] = pages

            # Extract text content from PDF files
            if file_name.lower().endswith('.pdf') and file_data.startswith('data:'):
                logger.info(f"Starting PDF text extraction for: {file_name}")
                try:
                    text_content = await self._extract_pdf_text(file_data, max_length=20000)  # Extract more text
                    if text_content:
                        file_info["text_content"] = text_content
                        logger.info(f"✅ Successfully extracted {len(text_content)} characters from PDF: {file_name}")
                        logger.info(f"Text preview (first 200 chars): {text_content[:200]}")
                    else:
                        logger.warning(f"⚠️ No text content extracted from PDF: {file_name} (may be image-based PDF)")
                except Exception as e:
                    logger.error(f"❌ Failed to extract PDF text from {file_name}: {e}", exc_info=True)

            return file_info
        except Exception as e:
            logger.error(f"Failed to process file: {e}", exc_info=True)
            return {
                "name": file_name,
                "size": file_size or 0,
                "type": file_type or "application/octet-stream",
                "error": str(e)
            }

    def _detect_mime_type(self, file_name: str) -> str:
        """Detect MIME type from file name"""
        mime_type, _ = mimetypes.guess_type(file_name)
        return mime_type or "application/octet-stream"

    def _detect_language(self, file_name: str) -> str:
        """Detect language from file name (simple heuristic)"""
        if any(char in file_name for char in ['中文', '繁體', '簡體', 'zh', 'TW', 'CN']):
            return "zh-TW"
        return "en"

    def _detect_file_type(self, file_name: str, mime_type: str) -> str:
        """Detect file type category"""
        file_name_lower = file_name.lower()

        if any(ext in file_name_lower for ext in ['.doc', '.docx', '.pdf']):
            if any(word in file_name_lower for word in ['proposal', '企劃', '提案', 'proposal']):
                return "proposal"
            if any(word in file_name_lower for word in ['report', '報告', 'report']):
                return "report"
            return "document"

        if any(ext in file_name_lower for ext in ['.md', '.txt']):
            return "text"

        if any(ext in file_name_lower for ext in ['.xls', '.xlsx']):
            return "spreadsheet"

        if any(ext in file_name_lower for ext in ['.ppt', '.pptx']):
            return "presentation"

        return "unknown"

    def _estimate_pages(self, file_name: str, file_size: Optional[int]) -> Optional[int]:
        """Estimate number of pages (rough estimate)"""
        if not file_size:
            return None

        file_name_lower = file_name.lower()

        if '.pdf' in file_name_lower:
            return max(1, file_size // 50000)
        elif '.docx' in file_name_lower or '.doc' in file_name_lower:
            return max(1, file_size // 30000)
        elif '.txt' in file_name_lower or '.md' in file_name_lower:
            return max(1, file_size // 2000)

        return None

    async def _extract_pdf_text(self, file_data: str, max_length: int = 10000) -> Optional[str]:
        """Extract text content from PDF file"""
        try:
            import tempfile
            import os

            # Decode base64 data
            if file_data.startswith('data:'):
                base64_data = file_data.split(',')[1] if ',' in file_data else file_data
                pdf_bytes = base64.b64decode(base64_data)
            else:
                return None

            # Try PyPDF2 first
            try:
                import PyPDF2
                from io import BytesIO

                pdf_file = BytesIO(pdf_bytes)
                pdf_reader = PyPDF2.PdfReader(pdf_file)

                text_parts = []
                # Extract text from more pages to get meaningful content (up to 20 pages)
                pages_to_extract = min(20, len(pdf_reader.pages))
                logger.info(f"Extracting text from {pages_to_extract} pages of PDF ({len(pdf_reader.pages)} total pages)")

                for page_num in range(pages_to_extract):
                    try:
                        page = pdf_reader.pages[page_num]
                        text = page.extract_text()
                        if text and text.strip():
                            text_parts.append(text.strip())
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num}: {e}")
                        continue

                extracted_text = '\n\n'.join(text_parts)
                if extracted_text:
                    logger.info(f"Successfully extracted {len(extracted_text)} characters from PDF")
                    return extracted_text[:max_length]
                else:
                    logger.warning("No text extracted from PDF pages")
            except ImportError:
                logger.warning("PyPDF2 not available, trying alternative method")

            # Fallback: Use LLM vision API if available
            # For now, return None if PyPDF2 is not available
            return None

        except Exception as e:
            logger.warning(f"Failed to extract PDF text: {e}")
            return None
