"""
Workspace Runtime Profile Store

Manages WorkspaceRuntimeProfile persistence using workspace.metadata field.
MVP implementation: no DB migration, stores in metadata JSON.
"""

from datetime import datetime
from typing import Optional
import logging

from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.models.workspace import Workspace
from backend.app.services.stores.postgres.workspaces_store import (
    PostgresWorkspacesStore,
)

logger = logging.getLogger(__name__)


class WorkspaceRuntimeProfileStore:
    """Store for managing workspace runtime profiles (MVP: uses workspace.metadata)"""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        self.db_path = db_path
        self.workspaces_store = PostgresWorkspacesStore(db_role=db_role)

    async def get_runtime_profile(
        self, workspace_id: str
    ) -> Optional[WorkspaceRuntimeProfile]:
        """
        Get runtime profile for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            WorkspaceRuntimeProfile or None if not found
        """
        workspace = await self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            return None

        return self._load_from_workspace(workspace)

    async def save_runtime_profile(
        self,
        workspace_id: str,
        profile: WorkspaceRuntimeProfile,
        updated_by: Optional[str] = None,
        updated_reason: Optional[str] = None,
    ) -> WorkspaceRuntimeProfile:
        """
        Save runtime profile for a workspace

        Args:
            workspace_id: Workspace ID
            profile: WorkspaceRuntimeProfile to save
            updated_by: User ID who updated (optional)
            updated_reason: Reason for update (optional)

        Returns:
            Saved WorkspaceRuntimeProfile
        """
        workspace = await self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        if updated_by:
            profile.updated_by = updated_by
        if updated_reason:
            profile.updated_reason = updated_reason
        profile.updated_at = datetime.utcnow()

        if workspace.metadata is None:
            workspace.metadata = {}

        try:
            profile_dict = profile.model_dump(mode="json")
        except AttributeError:
            profile_dict = profile.dict()

        workspace.metadata["runtime_profile"] = profile_dict

        await self.workspaces_store.update_workspace(workspace)

        return profile

    async def delete_runtime_profile(self, workspace_id: str) -> bool:
        """
        Delete runtime profile for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            True if deleted, False if not found
        """
        workspace = await self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            return False

        if workspace.metadata and "runtime_profile" in workspace.metadata:
            del workspace.metadata["runtime_profile"]
            await self.workspaces_store.update_workspace(workspace)
            return True

        return False

    def _load_from_workspace(
        self, workspace: Workspace
    ) -> Optional[WorkspaceRuntimeProfile]:
        """
        Load runtime profile from workspace metadata

        Args:
            workspace: Workspace object

        Returns:
            WorkspaceRuntimeProfile or None if not found
        """
        if not workspace.metadata or "runtime_profile" not in workspace.metadata:
            return None

        try:
            profile_data = workspace.metadata["runtime_profile"]
            profile = WorkspaceRuntimeProfile(**profile_data)
            profile.ensure_phase2_fields()
            return profile
        except Exception as e:
            logger.warning(
                f"Failed to parse runtime_profile from workspace {workspace.id}: {e}"
            )
            return None

    async def create_default_profile(
        self, workspace_id: str
    ) -> WorkspaceRuntimeProfile:
        """
        Create default runtime profile for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Default WorkspaceRuntimeProfile (with Phase 2 fields initialized)
        """
        from backend.app.models.workspace import ExecutionMode

        workspace = await self.workspaces_store.get_workspace(workspace_id)

        default_mode = ExecutionMode.QA
        if workspace and workspace.execution_mode:
            try:
                default_mode = ExecutionMode(workspace.execution_mode)
                logger.info(
                    "create_default_profile: Inheriting execution_mode=%s from workspace %s",
                    default_mode.value,
                    workspace_id,
                )
            except ValueError:
                logger.warning(
                    "create_default_profile: Invalid execution_mode '%s' in workspace %s, defaulting to QA",
                    workspace.execution_mode,
                    workspace_id,
                )

        profile = WorkspaceRuntimeProfile(default_mode=default_mode)
        profile.ensure_phase2_fields()
        return await self.save_runtime_profile(workspace_id, profile)
