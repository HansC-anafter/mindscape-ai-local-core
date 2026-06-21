"""Filesystem helpers for workspace file upload and analysis sidecars."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import base64
import hashlib
import json
import os
import uuid


@dataclass(frozen=True)
class FileHashResult:
    file_hash: Optional[str]
    file_path: Optional[str]


def store_uploaded_file(
    workspace_id: str,
    file_data: str,
    file_name: str,
    file_type: Optional[str],
    file_size: Optional[int],
    uploads_dir: Optional[str] = None,
    file_id_factory: Callable[[], str] | None = None,
) -> Dict[str, Any]:
    """Persist a base64 data URL and write its metadata sidecar."""
    if not file_data or not file_data.startswith("data:"):
        raise ValueError("Invalid file_data format, expected base64 data URL")

    _header, encoded = file_data.split(",", 1)
    file_content = base64.b64decode(encoded)
    file_hash = hashlib.sha256(file_content).hexdigest()
    file_id = file_id_factory() if file_id_factory else str(uuid.uuid4())

    workspace_uploads_dir = Path(uploads_dir or os.getenv("UPLOADS_DIR", "data/uploads"))
    workspace_uploads_dir = workspace_uploads_dir / workspace_id
    workspace_uploads_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(file_name).suffix if file_name else ""
    if not file_ext:
        file_ext = _extension_for_mime_type(file_type)

    file_path = workspace_uploads_dir / f"{file_id}{file_ext}"
    with open(file_path, "wb") as file_handle:
        file_handle.write(file_content)

    meta_path = workspace_uploads_dir / f"{file_id}.meta.json"
    with open(meta_path, "w") as meta_handle:
        json.dump(
            {
                "file_id": file_id,
                "original_name": file_name,
                "file_type": file_type,
                "file_size": file_size or len(file_content),
                "file_hash": file_hash,
            },
            meta_handle,
        )

    return {
        "file_id": file_id,
        "file_path": str(file_path),
        "file_name": file_name,
        "file_type": file_type,
        "file_size": file_size or len(file_content),
        "file_hash": file_hash,
    }


def resolve_file_path_by_id(
    file_id: str,
    uploads_dir: Optional[str] = None,
    file_path_lookup: Optional[Callable[[str], Optional[str]]] = None,
    log: Any = None,
) -> Optional[str]:
    """Resolve an uploaded file path from a file id."""
    try:
        if file_path_lookup is None:
            from backend.app.capabilities.core_files.services.upload import (
                get_file_path_by_id,
            )

            file_path_lookup = get_file_path_by_id
        return file_path_lookup(file_id)
    except (ImportError, AttributeError):
        uploads_path = Path(uploads_dir or os.getenv("UPLOADS_DIR", "data/uploads"))
        if uploads_path.exists():
            for uploaded_file in uploads_path.rglob(f"{file_id}.*"):
                file_path = str(uploaded_file)
                if log:
                    log.info(f"Found file_path for file_id {file_id}: {file_path}")
                return file_path
            if log:
                log.warning(
                    f"Could not find file_path for file_id {file_id} in {uploads_path}"
                )
    return None


def calculate_file_hash_for_analysis(
    file_path: Optional[str],
    file_data: Optional[str],
    file_id: Optional[str],
    workspace_id: str,
    file_name: str,
    uploads_dir: Optional[str] = None,
    log: Any = None,
) -> FileHashResult:
    """Calculate the analysis file hash using the existing precedence order."""
    if file_path:
        path = Path(file_path)
        if path.exists():
            try:
                file_hash = _hash_path(path)
                if log:
                    log.info(
                        f"Calculated file_hash for {file_name} from file_path: {file_hash[:16]}..."
                    )
                return FileHashResult(file_hash=file_hash, file_path=str(path))
            except Exception as exc:
                if log:
                    log.warning(
                        f"Failed to calculate file_hash from file_path {file_path}: {exc}"
                    )
        else:
            if log:
                log.warning(f"File path does not exist: {file_path}")
        return FileHashResult(file_hash=None, file_path=file_path)

    if file_data:
        try:
            _header, encoded = file_data.split(",", 1)
            file_content = base64.b64decode(encoded)
            file_hash = hashlib.sha256(file_content).hexdigest()
            if log:
                log.info(
                    f"Calculated file_hash for {file_name} from file_data: {file_hash[:16]}..."
                )
            return FileHashResult(file_hash=file_hash, file_path=file_path)
        except Exception as exc:
            if log:
                log.warning(f"Failed to calculate file_hash from file_data: {exc}")
            return FileHashResult(file_hash=None, file_path=file_path)

    if file_id:
        uploads_path = Path(uploads_dir or os.getenv("UPLOADS_DIR", "data/uploads"))
        uploads_path = uploads_path / workspace_id if workspace_id else uploads_path
        if uploads_path.exists():
            for uploaded_file in uploads_path.rglob(f"{file_id}.*"):
                try:
                    file_hash = _hash_path(uploaded_file)
                    if log:
                        log.info(
                            f"Calculated file_hash for {file_name} from file_id {file_id}: {file_hash[:16]}..."
                        )
                    return FileHashResult(
                        file_hash=file_hash,
                        file_path=str(uploaded_file),
                    )
                except Exception as exc:
                    if log:
                        log.warning(
                            f"Failed to calculate file_hash from file {uploaded_file}: {exc}"
                        )
                    continue
            if log:
                log.warning(f"Could not find file for file_id {file_id} in {uploads_path}")

    return FileHashResult(file_hash=None, file_path=file_path)


def write_analysis_sidecar(
    file_path: str,
    analysis_result: Dict[str, Any],
    event_id: str,
    file_hash: Optional[str],
    file_name: str,
    file_type: Optional[str],
    workspace_id: str,
) -> Path:
    """Write the analysis sidecar next to the uploaded file."""
    sidecar_path = Path(file_path).with_suffix(".analysis.json")
    sidecar_data = {
        "file_info": analysis_result.get("file_info", {}),
        "event_id": event_id,
        "file_hash": file_hash,
        "file_name": file_name,
        "file_type": file_type,
        "workspace_id": workspace_id,
    }
    sidecar_path.write_text(
        json.dumps(sidecar_data, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return sidecar_path


def _extension_for_mime_type(file_type: Optional[str]) -> str:
    if not file_type:
        return ""
    mime_to_ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "application/json": ".json",
    }
    return mime_to_ext.get(file_type, "")


def _hash_path(path: Path) -> str:
    with open(path, "rb") as file_handle:
        return hashlib.sha256(file_handle.read()).hexdigest()
