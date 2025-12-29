"""
Workspace Runtime Profile Store

Manages WorkspaceRuntimeProfile persistence using workspace.metadata field.
MVP implementation: no DB migration, stores in metadata JSON.
"""

from datetime import datetime
from typing import Optional
from backend.app.services.stores.base import StoreBase
from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.models.workspace import Workspace
from backend.app.services.stores.workspaces_store import WorkspacesStore
import logging

logger = logging.getLogger(__name__)


class WorkspaceRuntimeProfileStore(StoreBase):
    """Store for managing workspace runtime profiles (MVP: uses workspace.metadata)"""

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self.workspaces_store = WorkspacesStore(db_path)

    def get_runtime_profile(self, workspace_id: str) -> Optional[WorkspaceRuntimeProfile]:
        """
        Get runtime profile for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            WorkspaceRuntimeProfile or None if not found
        """
        workspace = self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            return None

        return self._load_from_workspace(workspace)

    def save_runtime_profile(
        self,
        workspace_id: str,
        profile: WorkspaceRuntimeProfile,
        updated_by: Optional[str] = None,
        updated_reason: Optional[str] = None
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
        workspace = self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Update profile metadata
        if updated_by:
            profile.updated_by = updated_by
        if updated_reason:
            profile.updated_reason = updated_reason
        profile.updated_at = datetime.utcnow()

        # Store in workspace.metadata
        if workspace.metadata is None:
            workspace.metadata = {}

        # Serialize profile to dict (compatible with both Pydantic v1 and v2)
        try:
            # Try Pydantic v2 model_dump()
            profile_dict = profile.model_dump(mode='json')
        except AttributeError:
            # Fallback to Pydantic v1 dict()
            profile_dict = profile.dict()

        workspace.metadata['runtime_profile'] = profile_dict

        # Update workspace
        self.workspaces_store.update_workspace(workspace)

        return profile

    def delete_runtime_profile(self, workspace_id: str) -> bool:
        """
        Delete runtime profile for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            True if deleted, False if not found
        """
        workspace = self.workspaces_store.get_workspace(workspace_id)
        if not workspace:
            return False

        if workspace.metadata and 'runtime_profile' in workspace.metadata:
            del workspace.metadata['runtime_profile']
            self.workspaces_store.update_workspace(workspace)
            return True

        return False

    def _load_from_workspace(self, workspace: Workspace) -> Optional[WorkspaceRuntimeProfile]:
        """
        Load runtime profile from workspace metadata

        Args:
            workspace: Workspace object

        Returns:
            WorkspaceRuntimeProfile or None if not found
        """
        if not workspace.metadata or 'runtime_profile' not in workspace.metadata:
            return None

        try:
            profile_data = workspace.metadata['runtime_profile']
            profile = WorkspaceRuntimeProfile(**profile_data)
            # Ensure Phase 2 fields are initialized (backward compatibility)
            profile.ensure_phase2_fields()
            return profile
        except Exception as e:
            logger.warning(f"Failed to parse runtime_profile from workspace {workspace.id}: {e}")
            return None

    def create_default_profile(self, workspace_id: str) -> WorkspaceRuntimeProfile:
        """
        Create default runtime profile for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Default WorkspaceRuntimeProfile (with Phase 2 fields initialized)
        """
        profile = WorkspaceRuntimeProfile()
        # Ensure Phase 2 fields are initialized
        profile.ensure_phase2_fields()
        return self.save_runtime_profile(workspace_id, profile)

