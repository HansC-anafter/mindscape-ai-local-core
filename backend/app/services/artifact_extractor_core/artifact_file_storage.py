"""File storage helpers for artifact extraction."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.models.workspace import ArtifactType

logger = logging.getLogger("backend.app.services.artifact_extractor_core.extractors")


def _utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _write_generated_artifact(
    service: Any,
    *,
    task: Any,
    playbook_code: str,
    intent_id: Optional[str],
    artifact_type: ArtifactType,
    title: str,
    content_bytes: bytes,
    log_label: str,
) -> tuple[Optional[str], bool, Optional[str]]:
    """Write generated artifact bytes into workspace storage."""
    storage_ref = None
    write_failed = False
    write_error = None

    try:
        storage_path = service._get_artifact_storage_path(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type.value,
        )

        filename = service._generate_artifact_filename(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type.value,
            title=title,
        )

        target_path = storage_path / filename
        conflict_info = service._check_file_conflict(
            target_path=target_path,
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type.value,
        )

        if conflict_info.get("has_conflict") and conflict_info.get("suggested_version"):
            filename = service._generate_artifact_filename(
                workspace_id=task.workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact_type.value,
                title=title,
                version=conflict_info["suggested_version"],
            )
            target_path = storage_path / filename

        service._write_artifact_file_atomic(content_bytes, target_path)
        storage_ref = str(target_path)
        logger.info("Successfully wrote %s artifact to %s", log_label, storage_ref)
    except Exception as exc:
        write_failed = True
        write_error = str(exc)
        logger.warning(
            "Failed to write %s artifact to workspace path: %s. "
            "Artifact will be created without file storage.",
            log_label,
            exc,
        )

    return storage_ref, write_failed, write_error


def _copy_source_file_artifact(
    service: Any,
    *,
    task: Any,
    source_file_path: str,
    playbook_code: str,
    intent_id: Optional[str],
    artifact_type: ArtifactType,
    title: str,
    log_label: str,
) -> str:
    """Copy an existing source file into workspace storage, with fallback."""
    try:
        storage_dir = service._get_artifact_storage_path(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type.value,
        )
    except (ValueError, PermissionError) as exc:
        logger.error("Failed to get storage path for %s artifact: %s", log_label, exc)
        logger.warning("Using original file path as storage_ref: %s", source_file_path)
        return source_file_path

    filename = service._generate_artifact_filename(
        workspace_id=task.workspace_id,
        playbook_code=playbook_code,
        artifact_type=artifact_type.value,
        title=title,
    )
    target_path = storage_dir / filename

    conflict_info = service._check_file_conflict(
        target_path=target_path,
        workspace_id=task.workspace_id,
        playbook_code=playbook_code,
        artifact_type=artifact_type.value,
        force=False,
    )

    if conflict_info.get("has_conflict") and conflict_info.get("suggested_version"):
        filename = service._generate_artifact_filename(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type.value,
            title=title,
            version=conflict_info["suggested_version"],
        )
        target_path = storage_dir / filename

    try:
        with service._file_lock(storage_dir):
            source_path = Path(source_file_path)
            if not source_path.exists():
                logger.warning(
                    "Source file not found: %s, using original path",
                    source_file_path,
                )
                return source_file_path

            file_content = source_path.read_bytes()
            service._write_artifact_file_atomic(file_content, target_path)
            storage_ref = str(target_path)
            logger.info("Successfully wrote %s artifact to %s", log_label, storage_ref)
            return storage_ref
    except Exception as exc:
        logger.error(
            "Failed to write %s artifact file: %s, using original path",
            log_label,
            exc,
        )
        return source_file_path
