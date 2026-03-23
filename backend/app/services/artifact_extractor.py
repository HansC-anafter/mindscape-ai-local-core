"""
Artifact Extractor Service

Extracts artifacts from playbook execution results and creates Artifact records.
Supports multiple playbook types with different output formats.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.app.models.workspace import Artifact, Task
from backend.app.services.artifact_extractor_core.extractors import (
    extract_audio_artifact,
    extract_campaign_asset_artifact,
    extract_content_drafting_artifact,
    extract_daily_planning_artifact,
    extract_generic_artifact,
    extract_major_proposal_artifact,
)
from backend.app.services.artifact_extractor_core.storage import (
    check_file_conflict,
    extract_version_from_filename,
    file_lock,
    generate_artifact_filename,
    get_allowed_directories,
    get_artifact_storage_path,
    get_extension_for_artifact_type,
    get_next_version,
    sanitize_filename,
    validate_path_in_allowed_directories,
    write_artifact_file_atomic,
)
from backend.app.services.mindscape_store import MindscapeStore


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

logger = logging.getLogger(__name__)


class ArtifactExtractor:
    """Extract artifacts from playbook execution results"""

    def __init__(self, store: MindscapeStore):
        """
        Initialize ArtifactExtractor

        Args:
            store: MindscapeStore instance for accessing workspace configuration
        """
        self.store = store

    def extract_artifact_from_task_result(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        playbook_code: str,
        intent_id: Optional[str] = None
    ) -> Optional[Artifact]:
        """
        Extract artifact from task execution result

        Args:
            task: Completed task
            execution_result: Execution result data
            playbook_code: Playbook code
            intent_id: Optional intent ID (extracted from execution_result or task)

        Returns:
            Artifact model or None if no artifact can be extracted
        """
        try:
            # Extract intent_id if not provided
            if not intent_id:
                intent_id = self._extract_intent_id(task, execution_result)

            # Route to specific extractor based on playbook_code
            playbook_lower = playbook_code.lower()

            if "daily_planning" in playbook_lower or "planning" in playbook_lower:
                return self._extract_daily_planning_artifact(task, execution_result, intent_id)
            elif "content_drafting" in playbook_lower or "draft" in playbook_lower:
                return self._extract_content_drafting_artifact(task, execution_result, intent_id)
            elif "major_proposal" in playbook_lower or "proposal" in playbook_lower:
                return self._extract_major_proposal_artifact(task, execution_result, intent_id)
            elif "campaign_asset" in playbook_lower or "canva" in playbook_lower:
                return self._extract_campaign_asset_artifact(task, execution_result, intent_id)
            elif "audio" in playbook_lower or "recording" in playbook_lower or "voice" in playbook_lower:
                return self._extract_audio_artifact(task, execution_result, intent_id)
            else:
                # Try generic extraction for unknown playbooks
                logger.debug(f"No specific extractor for playbook {playbook_code}, trying generic extraction")
                return self._extract_generic_artifact(task, execution_result, playbook_code, intent_id)

        except Exception as e:
            logger.error(f"Failed to extract artifact from task {task.id}: {e}", exc_info=True)
            return None

    def _extract_intent_id(
        self,
        task: Task,
        execution_result: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract intent_id from task or execution_result

        Priority:
        1. execution_result.intent_id
        2. task.intent_id (if exists)
        3. task.metadata.intent_id (if exists)

        Args:
            task: Task object
            execution_result: Execution result dict

        Returns:
            Intent ID or None
        """
        # Check execution_result first
        if isinstance(execution_result, dict):
            intent_id = execution_result.get("intent_id")
            if intent_id:
                return intent_id

        # Check task.intent_id (if Task model has this field)
        if hasattr(task, 'intent_id') and task.intent_id:
            return task.intent_id

        # Check task.metadata
        if hasattr(task, 'metadata') and isinstance(task.metadata, dict):
            intent_id = task.metadata.get("intent_id")
            if intent_id:
                return intent_id

        return None

    def _extract_daily_planning_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """Delegate daily planning extraction to the Wave B helper module."""
        return extract_daily_planning_artifact(
            self,
            task,
            execution_result,
            intent_id,
        )

    def _extract_content_drafting_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """Delegate content drafting extraction to the Wave B helper module."""
        return extract_content_drafting_artifact(
            self,
            task,
            execution_result,
            intent_id,
        )

    def _extract_major_proposal_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """Delegate proposal extraction to the Wave B helper module."""
        return extract_major_proposal_artifact(
            self,
            task,
            execution_result,
            intent_id,
        )

    def _extract_campaign_asset_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """Delegate campaign asset extraction to the Wave B helper module."""
        return extract_campaign_asset_artifact(
            self,
            task,
            execution_result,
            intent_id,
        )

    def _extract_audio_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """Delegate audio extraction to the Wave B helper module."""
        return extract_audio_artifact(
            self,
            task,
            execution_result,
            intent_id,
        )

    def _extract_generic_artifact(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        playbook_code: str,
        intent_id: Optional[str]
    ) -> Optional[Artifact]:
        """Delegate generic extraction to the Wave B helper module."""
        return extract_generic_artifact(
            self,
            task,
            execution_result,
            playbook_code,
            intent_id,
        )

    def _get_artifact_storage_path(
        self,
        workspace_id: str,
        playbook_code: str,
        intent_id: Optional[str] = None,
        artifact_type: str = "file",
        execution_storage_config: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Get artifact storage path with priority resolution (execution → playbook → workspace → default)

        Path structure:
        <base_path>/<artifacts_dir>/<playbook_code>/[<intent_id>/][<date>/]

        Security requirement: Must validate path is within allowed directories

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            intent_id: Optional intent ID (for bucketing)
            artifact_type: Artifact type (for extension)
            execution_storage_config: Optional execution-specific storage config

        Returns:
            Path object pointing to storage directory
        """
        return get_artifact_storage_path(
            store=self.store,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type,
            execution_storage_config=execution_storage_config,
            logger_instance=logger,
        )

    def _get_allowed_directories(self) -> List[str]:
        """Return the configured allowed directories from workspace helpers."""
        return get_allowed_directories()

    def _validate_path_in_allowed_directories(
        self,
        path: Path,
        allowed_directories: List[str]
    ) -> bool:
        """Validate if path is within allowed directories (reuse function from workspace.py)"""
        return validate_path_in_allowed_directories(path, allowed_directories)

    def _sanitize_filename(self, filename: str, max_length: int = 200) -> str:
        """
        Sanitize a filename for cross-platform artifact writes.

        Args:
            filename: Original filename
            max_length: Maximum filename length

        Returns:
            Sanitized filename
        """
        return sanitize_filename(filename, max_length=max_length)

    def _generate_artifact_filename(
        self,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        title: str,
        version: Optional[int] = None,
        extension: Optional[str] = None
    ) -> str:
        """
        Generate the artifact filename.

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            artifact_type: Artifact type
            title: Artifact title used for slug generation
            version: Optional explicit version override
            extension: Optional explicit file extension override

        Returns:
            Sanitized artifact filename
        """
        return generate_artifact_filename(
            store=self.store,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
            title=title,
            version=version,
            extension=extension,
        )

    def _get_next_version(
        self,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str
    ) -> int:
        """
        Get next version number

        Query DB for latest version of same playbook and artifact_type, return next version number.

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            artifact_type: Artifact type

        Returns:
            Next version number (starting from 1)
        """
        return get_next_version(
            store=self.store,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
        )

    def _get_extension_for_artifact_type(self, artifact_type: str) -> str:
        """
        Get file extension based on artifact_type

        Args:
            artifact_type: Artifact type (string or ArtifactType enum value)

        Returns:
            File extension string (without dot)
        """
        return get_extension_for_artifact_type(artifact_type)

    def _write_artifact_file_atomic(
        self,
        content: bytes,
        target_path: Path
    ) -> None:
        """
        Atomically write file

        Uses temp file + fsync + rename to ensure atomicity, avoiding file corruption during write.

        Args:
            content: Content to write (bytes)
            target_path: Target file path

        Raises:
            OSError: If write fails
        """
        write_artifact_file_atomic(
            content=content,
            target_path=target_path,
            logger_instance=logger,
        )

    @staticmethod
    def _file_lock(lock_path: Path, timeout: int = 10):
        """
        File lock context manager

        Uses portalocker to implement cross-platform file locking (at directory level), preventing concurrent write conflicts.

        Args:
            lock_path: Directory where lock file is located
            timeout: Timeout for acquiring lock (seconds)

        Yields:
            None (used as context manager)

        Raises:
            ImportError: If portalocker is not installed
            TimeoutError: If lock acquisition times out

        Usage:
            with ArtifactExtractor._file_lock(storage_path):
                # Execute file write operation
                pass
        """
        return file_lock(
            lock_path,
            timeout=timeout,
            logger_instance=logger,
        )

    def _check_file_conflict(
        self,
        target_path: Path,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Check whether the target artifact path conflicts with an existing file.

        Args:
            target_path: Target file path
            workspace_id: Workspace ID used for version lookup
            playbook_code: Playbook code used for version lookup
            artifact_type: Artifact type used for version lookup
            force: Whether the caller allows overwrite mode

        Returns:
            Conflict metadata with `has_conflict` and `suggested_version`
        """
        return check_file_conflict(
            store=self.store,
            target_path=target_path,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
            force=force,
            logger_instance=logger,
        )

    def _extract_version_from_filename(self, filename: str) -> Optional[int]:
        """
        Extract version number from filename

        Filename format: <slug>-v<number>-<timestamp>.<ext>
        Extract version number from it.

        Args:
            filename: Filename (without path)

        Returns:
            Version number (None if extraction fails)
        """
        return extract_version_from_filename(filename)
