"""
File Dispatch Enricher — enrich file metadata for dispatch context

Reads file analysis results from .analysis.json sidecars and queries
PackCapabilityIndex to recommend relevant capability packs.
Produces structured file_hint + recommended_pack_codes for downstream
RAG tool selection.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileDispatchContext:
    """Enriched file context for dispatch."""

    files: List[Dict[str, Any]]
    recommended_pack_codes: List[str]
    file_hint: str


class FileDispatchEnricher:
    """Enrich dispatch context with file analysis + pack recommendations."""

    def __init__(self, pack_index=None):
        if pack_index is None:
            from backend.app.services.pack_capability_index import (
                PackCapabilityIndex,
            )

            pack_index = PackCapabilityIndex()
        self.pack_index = pack_index

    async def enrich(
        self,
        workspace_id: str,
        uploaded_files: List[Dict[str, Any]],
    ) -> FileDispatchContext:
        """
        Enrich uploaded file metadata with:
        1. detected_type from FileProcessor
        2. text_content_preview from .analysis.json sidecar
        3. recommended_packs from PackCapabilityIndex
        4. file_hint string for MINDSCAPE_TASK_HINT enrichment
        """
        all_pack_codes: set = set()
        hint_parts: List[str] = []

        for f in uploaded_files:
            file_name = f.get("file_name", "")
            file_path = f.get("file_path", "")

            # 1. Detect type from extension + MIME (quick, no DB)
            detected_type = self._detect_type(file_name, f.get("file_type", ""))
            f["detected_type"] = detected_type

            # 2. Read .analysis.json sidecar if exists
            if file_path:
                self._read_analysis_sidecar(f, file_path)

            # 3. Pack recommendations
            packs = self.pack_index.get_packs_for_file_type(detected_type)
            f["recommended_packs"] = packs
            all_pack_codes.update(packs)

            # 4. Build hint fragment
            if detected_type and detected_type != "unknown":
                hint_parts.append(f"[{detected_type}: {file_name}]")
            elif file_name:
                hint_parts.append(f"[file: {file_name}]")

        file_hint = " ".join(hint_parts)
        recommended = sorted(all_pack_codes)

        if recommended:
            logger.info(
                f"FileDispatchEnricher: {len(uploaded_files)} files → "
                f"packs={recommended}, hint={file_hint!r}"
            )

        return FileDispatchContext(
            files=uploaded_files,
            recommended_pack_codes=recommended,
            file_hint=file_hint,
        )

    @staticmethod
    def _detect_type(file_name: str, mime_type: str) -> str:
        """Quick file type detection (mirrors FileProcessor._detect_file_type)."""
        try:
            from backend.app.services.file_processor import FileProcessor

            fp = FileProcessor()
            return fp._detect_file_type(file_name, mime_type)
        except Exception:
            # Fallback: basic extension-based detection
            name_lower = file_name.lower()
            if any(
                ext in name_lower for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]
            ):
                return "video"
            if any(
                ext in name_lower for ext in [".mp3", ".wav", ".m4a", ".flac", ".ogg"]
            ):
                return "audio"
            if any(
                ext in name_lower for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]
            ):
                return "image"
            if any(ext in name_lower for ext in [".pdf", ".doc", ".docx"]):
                return "document"
            return "unknown"

    @staticmethod
    def _read_analysis_sidecar(f: Dict[str, Any], file_path: str) -> None:
        """Read .analysis.json sidecar and merge into file dict."""
        try:
            sidecar_path = Path(file_path).with_suffix(".analysis.json")
            if not sidecar_path.exists():
                return

            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            file_info = data.get("file_info", {})

            text_content = file_info.get("text_content") or ""
            if text_content:
                f["text_content_preview"] = text_content[:500]

            transcription_lang = file_info.get("transcription_language")
            if transcription_lang:
                f["transcription_language"] = transcription_lang

            # Carry over detected_type from analysis if more specific
            analysis_type = file_info.get("detected_type")
            if analysis_type and analysis_type != "unknown":
                f["detected_type"] = analysis_type

        except Exception as e:
            logger.debug(f"Failed to read analysis sidecar for {file_path}: {e}")
