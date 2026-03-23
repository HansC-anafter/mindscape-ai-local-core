"""Storage and naming helpers for artifact extraction."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.models.workspace import ArtifactType
from backend.app.services.storage_path_resolver import StoragePathResolver

logger = logging.getLogger(__name__)


def get_allowed_directories() -> List[str]:
    """Return the configured allowed storage directories."""
    from backend.app.routes.core.workspace import _get_allowed_directories

    return _get_allowed_directories()


def validate_path_in_allowed_directories(
    path: Path,
    allowed_directories: List[str],
) -> bool:
    """Return whether *path* stays inside the configured allowed roots."""
    from backend.app.routes.core.workspace import _validate_path_in_allowed_directories

    return _validate_path_in_allowed_directories(path, allowed_directories)


def get_artifact_storage_path(
    *,
    store: Any,
    workspace_id: str,
    playbook_code: str,
    intent_id: Optional[str] = None,
    artifact_type: str = "file",
    execution_storage_config: Optional[Dict[str, Any]] = None,
    logger_instance: Optional[logging.Logger] = None,
) -> Path:
    """Resolve and validate the artifact storage directory."""
    active_logger = logger_instance or logger

    workspace = store.workspaces.get_workspace(workspace_id)
    if not workspace:
        raise ValueError(f"Workspace not found: {workspace_id}")

    storage_path = StoragePathResolver.get_artifact_storage_path(
        workspace=workspace,
        playbook_code=playbook_code,
        intent_id=intent_id,
        artifact_type=artifact_type,
        execution_storage_config=execution_storage_config,
    )

    allowed_dirs = get_allowed_directories()
    if allowed_dirs:
        if not validate_path_in_allowed_directories(storage_path, allowed_dirs):
            raise ValueError(
                f"Storage path {storage_path} is not within allowed directories. "
                "This may indicate a security issue or misconfiguration."
            )
    else:
        active_logger.warning(
            "No allowed directories configured for workspace %s. "
            "Path validation skipped. This may be a security risk.",
            workspace_id,
        )

    return storage_path


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize a filename for cross-platform artifact writes."""
    illegal_chars = r'[<>:"|?*\x00/]'
    sanitized = re.sub(illegal_chars, "-", filename)

    reserved_names = [
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    ]

    base_name = sanitized.split(".")[0].upper()
    if base_name in reserved_names:
        sanitized = f"file-{sanitized}"

    sanitized = sanitized.strip(". ")

    if len(sanitized) > max_length:
        if "." in sanitized:
            name, ext = sanitized.rsplit(".", 1)
            max_name_length = max_length - len(ext) - 1
            sanitized = name[:max_name_length] + "." + ext
        else:
            sanitized = sanitized[:max_length]

    if not sanitized or sanitized == ".":
        sanitized = "file"

    return sanitized


def get_extension_for_artifact_type(artifact_type: str) -> str:
    """Return the default extension for an artifact type."""
    if isinstance(artifact_type, ArtifactType):
        artifact_type = artifact_type.value

    extension_map = {
        "docx": "docx",
        "draft": "md",
        "checklist": "md",
        "config": "json",
        "audio": "mp3",
        "canva": "url",
    }
    return extension_map.get(artifact_type, "txt")


def get_next_version(
    *,
    store: Any,
    workspace_id: str,
    playbook_code: str,
    artifact_type: str,
) -> int:
    """Return the next artifact version for the workspace/playbook/type tuple."""
    artifacts = store.artifacts.list_artifacts_by_playbook(workspace_id, playbook_code)
    same_type_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.artifact_type.value == artifact_type
        or str(artifact.artifact_type) == artifact_type
    ]

    if not same_type_artifacts:
        return 1

    max_version = 1
    for artifact in same_type_artifacts:
        version = artifact.metadata.get("version", 1) if artifact.metadata else 1
        if isinstance(version, int) and version > max_version:
            max_version = version

    return max_version + 1


def generate_artifact_filename(
    *,
    store: Any,
    workspace_id: str,
    playbook_code: str,
    artifact_type: str,
    title: str,
    version: Optional[int] = None,
    extension: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> str:
    """Generate a sanitized artifact filename."""
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[-\s]+", "-", slug)
    slug = slug[:50]
    if not slug:
        slug = playbook_code.lower()[:50]

    if version is None:
        version = get_next_version(
            store=store,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
        )

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if extension is None:
        extension = get_extension_for_artifact_type(artifact_type)

    filename = f"{slug}-v{version}-{timestamp}.{extension}"
    return sanitize_filename(filename, max_length=200)


def write_artifact_file_atomic(
    *,
    content: bytes,
    target_path: Path,
    logger_instance: Optional[logging.Logger] = None,
) -> None:
    """Atomically write artifact bytes to disk."""
    active_logger = logger_instance or logger
    temp_file = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=target_path.parent,
        delete=False,
        suffix=".tmp",
    )

    try:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.rename(temp_file.name, str(target_path))
        active_logger.debug("Atomically wrote file: %s", target_path)
    except Exception:
        if os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception as cleanup_error:
                active_logger.warning(
                    "Failed to cleanup temp file %s: %s",
                    temp_file.name,
                    cleanup_error,
                )
        raise


def file_lock(
    lock_path: Path,
    *,
    timeout: int = 10,
    logger_instance: Optional[logging.Logger] = None,
):
    """Return a cross-platform file lock context manager."""
    active_logger = logger_instance or logger

    try:
        import portalocker
    except ImportError as exc:
        raise ImportError(
            "portalocker is required for cross-platform file locking. "
            "Install it with: pip install portalocker>=2.0.0"
        ) from exc

    @contextmanager
    def _lock_context():
        lock_file = lock_path / ".artifact.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        lock_fd = None
        try:
            lock_fd = open(lock_file, "w")
            start_time = time.time()
            while True:
                try:
                    portalocker.lock(
                        lock_fd,
                        portalocker.LOCK_EX | portalocker.LOCK_NB,
                    )
                    break
                except (BlockingIOError, OSError):
                    if time.time() - start_time > timeout:
                        raise TimeoutError(
                            f"Failed to acquire lock on {lock_path} after {timeout}s"
                        )
                    time.sleep(0.1)

            yield
        finally:
            if lock_fd:
                try:
                    portalocker.unlock(lock_fd)
                except Exception as unlock_error:
                    active_logger.warning(
                        "Failed to unlock file: %s",
                        unlock_error,
                    )
                try:
                    lock_fd.close()
                except Exception as close_error:
                    active_logger.warning(
                        "Failed to close lock file: %s",
                        close_error,
                    )

    return _lock_context()


def check_file_conflict(
    *,
    store: Any,
    target_path: Path,
    workspace_id: str,
    playbook_code: str,
    artifact_type: str,
    force: bool = False,
    logger_instance: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Return conflict metadata for a target artifact path."""
    active_logger = logger_instance or logger

    if not target_path.exists():
        return {"has_conflict": False, "suggested_version": None}

    if force:
        active_logger.warning(
            "File conflict detected at %s, force=True will overwrite existing file",
            target_path,
        )
        return {"has_conflict": True, "suggested_version": None}

    try:
        suggested_version = get_next_version(
            store=store,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
        )
        active_logger.info(
            "File conflict detected at %s, suggested version: %s",
            target_path,
            suggested_version,
        )
        return {"has_conflict": True, "suggested_version": suggested_version}
    except Exception as exc:
        active_logger.warning(
            "Failed to get next version for conflict resolution: %s, "
            "falling back to timestamp-based naming",
            exc,
        )
        return {"has_conflict": True, "suggested_version": None}


def extract_version_from_filename(filename: str) -> Optional[int]:
    """Extract the version component from a generated artifact filename."""
    match = re.search(r"-v(\d+)-", filename)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None
