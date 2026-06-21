"""Document version history persistence helpers."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import hashlib
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def track_document_version(
    document_id: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    persist: bool = True,
    storage_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Track document version.

    Args:
        document_id: Document identifier
        content: Document content
        metadata: Optional metadata
        persist: Whether to persist to storage
        storage_dir: Storage directory

    Returns:
        Version tracking info
    """
    content_hash = calculate_content_hash(content)
    version_info = {
        "document_id": document_id,
        "content_hash": content_hash,
        "content_length": len(content),
        "version_timestamp": _utc_now().isoformat(),
        "metadata": metadata or {},
    }

    if persist:
        storage_dir_path = _version_storage_dir(storage_dir)
        storage_dir_path.mkdir(parents=True, exist_ok=True)

        safe_document_id = sanitize_document_id(document_id)
        history_file = storage_dir_path / f"{safe_document_id}.json"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as file_handle:
                    history = json.load(file_handle)
            else:
                history = {"document_id": document_id, "versions": []}

            history["versions"].append(version_info)
            history["last_updated"] = _utc_now().isoformat()

            if len(history["versions"]) > 50:
                history["versions"] = history["versions"][-50:]

            with open(history_file, "w", encoding="utf-8") as file_handle:
                json.dump(history, file_handle, indent=2, ensure_ascii=False)

            logger.debug(f"Saved version for document {document_id}")
        except Exception as exc:
            logger.error(
                f"Failed to save version for {document_id}: {exc}",
                exc_info=True,
            )

    logger.info(f"Tracked version for document {document_id}: hash={content_hash[:8]}...")
    return version_info


def sanitize_document_id(document_id: str) -> str:
    """
    Sanitize document_id for use as filename.

    Args:
        document_id: Original document identifier

    Returns:
        Sanitized identifier safe for filesystem
    """
    if "/" in document_id or "\\" in document_id or ":" in document_id:
        safe_hash = hashlib.sha256(document_id.encode("utf-8")).hexdigest()[:16]
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", document_id[:20])
        return f"{safe_prefix}_{safe_hash}"
    return re.sub(r"[^a-zA-Z0-9._-]", "_", document_id)


def get_document_version_history(
    document_id: str,
    storage_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get document version history.

    Args:
        document_id: Document identifier
        storage_dir: Storage directory

    Returns:
        List of version history entries
    """
    storage_dir_path = _version_storage_dir(storage_dir)
    storage_dir_path.mkdir(parents=True, exist_ok=True)

    safe_document_id = sanitize_document_id(document_id)
    history_file = storage_dir_path / f"{safe_document_id}.json"

    if not history_file.exists():
        logger.debug(f"No version history found for document {document_id}")
        return []

    try:
        with open(history_file, "r", encoding="utf-8") as file_handle:
            history = json.load(file_handle)
        return history.get("versions", [])
    except Exception as exc:
        logger.error(
            f"Failed to load version history for {document_id}: {exc}",
            exc_info=True,
        )
        return []


def get_latest_document_version(
    document_id: str,
    storage_dir: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get the latest version of a document.

    Args:
        document_id: Document identifier
        storage_dir: Storage directory

    Returns:
        Latest version info or None
    """
    history = get_document_version_history(document_id, storage_dir)
    if not history:
        return None
    return history[-1]


def calculate_content_hash(content: str) -> str:
    """Calculate SHA256 hash for document content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _version_storage_dir(storage_dir: Optional[str]) -> Path:
    return Path(storage_dir or os.getenv("DOCUMENT_VERSION_STORAGE", "/tmp/document_versions"))
