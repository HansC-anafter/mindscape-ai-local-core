"""
Storage Path Resolver Service

Resolves storage paths for playbook executions and artifacts with priority:
1. execution.storage_config (highest priority)
2. workspace.playbook_storage_config[playbook_code] (playbook-specific)
3. workspace.storage_base_path + workspace.artifacts_dir (workspace default)
4. System default path
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)


class StoragePathResolver:
    """Resolve storage paths for playbook executions and artifacts"""

    @staticmethod
    def get_storage_path_for_execution(
        workspace: Workspace,
        playbook_code: str,
        execution_storage_config: Optional[Dict[str, Any]] = None
    ) -> tuple[str, str]:
        """
        Get storage path for execution with priority:
        1. execution.storage_config (highest)
        2. workspace.playbook_storage_config[playbook_code]
        3. workspace.storage_base_path + workspace.artifacts_dir
        4. Default system path

        Args:
            workspace: Workspace model
            playbook_code: Playbook code
            execution_storage_config: Optional execution-specific storage config

        Returns:
            Tuple of (base_path, artifacts_dir)
        """
        # Priority 1: Execution-specific
        if execution_storage_config:
            base_path = execution_storage_config.get('base_path')
            artifacts_dir = execution_storage_config.get('artifacts_dir')
            if base_path:
                return (
                    base_path,
                    artifacts_dir or workspace.artifacts_dir or 'artifacts'
                )

        # Priority 2: Playbook-specific
        if workspace.playbook_storage_config:
            playbook_config = workspace.playbook_storage_config.get(playbook_code)
            if playbook_config:
                base_path = playbook_config.get('base_path')
                artifacts_dir = playbook_config.get('artifacts_dir')
                if base_path:
                    return (
                        base_path,
                        artifacts_dir or workspace.artifacts_dir or 'artifacts'
                    )

        # Priority 3: Workspace default
        if workspace.storage_base_path:
            return (
                workspace.storage_base_path,
                workspace.artifacts_dir or 'artifacts'
            )

        # Priority 4: System default
        default_path = os.path.expanduser("~/Documents/Mindscape")
        return (default_path, 'artifacts')

    @staticmethod
    def get_artifact_storage_path(
        workspace: Workspace,
        playbook_code: str,
        intent_id: Optional[str] = None,
        artifact_type: str = "file",
        execution_storage_config: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Get full artifact storage path with priority resolution

        Path structure:
        <base_path>/<artifacts_dir>/<playbook_code>/[<intent_id>/][<date>/]

        Args:
            workspace: Workspace model
            playbook_code: Playbook code
            intent_id: Optional intent ID (for bucketing)
            artifact_type: Artifact type (for extension)
            execution_storage_config: Optional execution-specific storage config

        Returns:
            Path object pointing to storage directory
        """
        # Get base path and artifacts_dir with priority
        base_path, artifacts_dir = StoragePathResolver.get_storage_path_for_execution(
            workspace=workspace,
            playbook_code=playbook_code,
            execution_storage_config=execution_storage_config
        )

        # Build path
        base_path_resolved = Path(base_path).expanduser().resolve()
        storage_path = base_path_resolved / artifacts_dir / playbook_code

        # Determine bucket strategy from storage_config
        storage_config = workspace.storage_config or {}
        if isinstance(storage_config, str):
            import json
            try:
                storage_config = json.loads(storage_config)
            except json.JSONDecodeError:
                storage_config = {}

        bucket_strategy = storage_config.get("bucket_strategy", "playbook_code")

        # Support multi-level bucket: playbook_code/intent_id/date
        if isinstance(bucket_strategy, list):
            for strategy in bucket_strategy:
                if strategy == "intent_id" and intent_id:
                    storage_path = storage_path / intent_id
                elif strategy == "date":
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    storage_path = storage_path / date_str
                elif strategy == "playbook_code":
                    # playbook_code already in base path, skip
                    pass
        else:
            # Single strategy (backward compatible)
            if bucket_strategy == "intent_id" and intent_id:
                storage_path = storage_path / intent_id
            elif bucket_strategy == "date":
                date_str = datetime.now().strftime("%Y-%m-%d")
                storage_path = storage_path / date_str
            # Default: playbook_code already in base path

        # If combined strategy configured but not using list, combine playbook_code/intent_id/date
        if not isinstance(bucket_strategy, list) and storage_config.get("enable_multi_level_bucket", False):
            if intent_id:
                storage_path = storage_path / intent_id
            date_str = datetime.now().strftime("%Y-%m-%d")
            storage_path = storage_path / date_str

        # Ensure directory exists
        storage_path.mkdir(parents=True, exist_ok=True)

        # Verify directory is writable
        if not os.access(storage_path, os.W_OK):
            raise PermissionError(
                f"Cannot write to directory {storage_path}: permission denied. "
                "Please check directory permissions or choose a different storage path."
            )

        return storage_path

