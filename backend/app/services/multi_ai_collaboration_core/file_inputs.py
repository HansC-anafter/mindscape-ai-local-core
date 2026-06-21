"""File input helpers for multi-AI collaboration."""

from __future__ import annotations

import base64
import logging
import os
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MEDIA_TRANSCRIPTION_EXTENSIONS = (
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".ogg",
    ".aac",
)

ToolExecutorFactory = Callable[[], Any]
SttProviderFactory = Callable[[], Any]


def _default_tool_executor_factory() -> Any:
    from backend.app.shared.tool_executor import ToolExecutor

    return ToolExecutor()


def _default_stt_provider_factory() -> Any:
    from backend.app.shared.audio.stt.factory import get_stt_provider

    return get_stt_provider()


def is_media_transcription_file(file_name: str) -> bool:
    """Return whether the file extension should attempt STT enrichment."""
    file_name_lower = file_name.lower()
    return any(
        file_name_lower.endswith(extension)
        for extension in MEDIA_TRANSCRIPTION_EXTENSIONS
    )


async def build_file_info(
    *,
    file_processor: Any,
    file_data: str,
    file_name: str,
    file_type: Optional[str],
    file_size: Optional[int],
    file_path: Optional[str] = None,
    tool_executor_factory: Optional[ToolExecutorFactory] = None,
    stt_provider_factory: Optional[SttProviderFactory] = None,
) -> Dict[str, Any]:
    """Build normalized file info with existing OCR and STT fallbacks."""
    if file_path and file_name.lower().endswith(".pdf"):
        logger.info("Using file path for extraction with OCR support: %s", file_path)
        try:
            executor_factory = tool_executor_factory or _default_tool_executor_factory
            executor = executor_factory()
            extract_result = await executor.execute_tool(
                "core_files.extract_text",
                file_path=file_path,
                file_type="pdf",
            )
            file_info = {
                "name": file_name,
                "size": file_size or 0,
                "type": file_type or "application/pdf",
                "text_content": extract_result.get("text", ""),
                "ocr_used": extract_result.get("ocr_used", False),
                "quality": extract_result.get("quality"),
                "file_path": file_path,
            }
            logger.info(
                "Extracted text using OCR-aware extraction: %s chars, OCR used: %s",
                len(file_info.get("text_content", "")),
                file_info.get("ocr_used", False),
            )
            return file_info
        except Exception as exc:
            logger.warning(
                "Failed to extract text with OCR integration: %s, "
                "falling back to standard processing",
                exc,
            )
            return await file_processor.process_file(
                file_data=file_data,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
            )

    if file_path and is_media_transcription_file(file_name):
        logger.info("Using Whisper STT for audio/video transcription: %s", file_path)
        file_info = await file_processor.process_file(
            file_data=file_data,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
        )
        try:
            provider_factory = stt_provider_factory or _default_stt_provider_factory
            stt = provider_factory()
            transcription = await stt.transcribe(file_path)
            transcribed_text = transcription.get("text", "")
            if transcribed_text and len(transcribed_text.strip()) > 20:
                file_info["text_content"] = transcribed_text
                file_info["transcription_language"] = transcription.get(
                    "language", "unknown"
                )
                file_info["transcription_segments"] = transcription.get(
                    "segments", []
                )
                file_info["file_path"] = file_path
                logger.info(
                    "Whisper transcription: %s chars, lang=%s",
                    len(transcribed_text),
                    transcription.get("language"),
                )
            else:
                logger.warning(
                    "Whisper returned insufficient text for %s",
                    file_name,
                )
        except Exception as exc:
            logger.warning(
                "Whisper STT failed for %s: %s, continuing without transcription",
                file_name,
                exc,
            )
        return file_info

    return await file_processor.process_file(
        file_data=file_data,
        file_name=file_name,
        file_type=file_type,
        file_size=file_size,
    )


def extract_content_preview(file_data: str, max_length: int = 2000) -> Optional[str]:
    """Extract text preview from base64 data URLs."""
    try:
        if file_data.startswith("data:"):
            base64_data = file_data.split(",")[1] if "," in file_data else file_data
            decoded = base64.b64decode(base64_data)
            text = decoded.decode("utf-8", errors="ignore")
            return text[:max_length]
        return None
    except Exception as exc:
        logger.warning("Failed to extract content preview: %s", exc)
        return None


async def extract_pdf_from_path(
    file_path: str,
    max_length: int = 10000,
) -> Optional[str]:
    """Extract text from a PDF file path."""
    try:
        import PyPDF2

        if not os.path.exists(file_path):
            logger.warning("PDF file path does not exist: %s", file_path)
            return None

        with open(file_path, "rb") as pdf_file:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text_parts = []
            for page_num in range(min(20, len(pdf_reader.pages))):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(text.strip())

            extracted_text = "\n\n".join(text_parts)
            if extracted_text:
                logger.info(
                    "Extracted %s chars from PDF file (%s pages)",
                    len(extracted_text),
                    len(pdf_reader.pages),
                )
                return extracted_text[:max_length]

        return None
    except ImportError:
        logger.error("PyPDF2 not installed. Cannot extract PDF text.")
        return None
    except Exception as exc:
        logger.warning("Failed to extract PDF text from path %s: %s", file_path, exc)
        return None


async def extract_pdf_text_direct(
    file_data: str,
    max_length: int = 10000,
) -> Optional[str]:
    """Extract text directly from PDF base64 data."""
    try:
        import PyPDF2

        if not file_data.startswith("data:"):
            return None

        base64_data = file_data.split(",")[1] if "," in file_data else file_data
        pdf_bytes = base64.b64decode(base64_data)

        pdf_file = BytesIO(pdf_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)

        text_parts = []
        for page_num in range(min(20, len(pdf_reader.pages))):
            page = pdf_reader.pages[page_num]
            text = page.extract_text()
            if text and text.strip():
                text_parts.append(text.strip())

        extracted_text = "\n\n".join(text_parts)
        if extracted_text:
            logger.info(
                "Extracted %s chars from PDF (%s pages)",
                len(extracted_text),
                len(pdf_reader.pages),
            )
            return extracted_text[:max_length]

        return None
    except ImportError:
        logger.error("PyPDF2 not installed. Cannot extract PDF text.")
        return None
    except Exception as exc:
        logger.warning("Failed to extract PDF text directly: %s", exc)
        return None


def infer_intents_from_filename(file_name: str, locale: str = "en") -> List[str]:
    """Infer potential intents from a filename when content extraction fails."""
    from backend.app.services.i18n_service import get_i18n_service

    if not file_name:
        return []

    i18n = get_i18n_service(default_locale=locale)
    intents = []
    file_name_lower = file_name.lower()

    intent_keywords_str = i18n.t(
        "multi_ai_collaboration",
        "intent_keywords.mapping",
        default=(
            "research:Research and Analysis,analysis:Analysis and Evaluation,"
            "plan:Planning,strategy:Strategy Development,"
            "development:Product Development,management:Project Management,"
            "writing:Content Writing,proposal:Proposal Development,"
            "report:Report Writing,marketing:Marketing Strategy,"
            "product:Product Development,project:Project Management"
        ),
    )

    intent_keywords = {}
    for pair in intent_keywords_str.split(","):
        if ":" in pair:
            keyword, intent = pair.split(":", 1)
            intent_keywords[keyword.strip()] = intent.strip()

    for keyword, intent in intent_keywords.items():
        if keyword in file_name_lower:
            intents.append(intent)
            break

    if not intents:
        name_without_ext = (
            file_name.rsplit(".", 1)[0] if "." in file_name else file_name
        )
        cleaned = (
            name_without_ext.replace("-", " ")
            .replace("_", " ")
            .replace("(", "")
            .replace(")", "")
        )
        words = cleaned.split()
        if words:
            first_phrase = " ".join(words[:3]) if len(words) > 1 else words[0]
            if len(first_phrase) > 3:
                intents.append(first_phrase[:50])

    return intents[:2]
