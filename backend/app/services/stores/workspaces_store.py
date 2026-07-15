"""
Workspaces store for Mindscape data persistence
Handles workspace CRUD operations
"""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from backend.app.services.stores.workspace_row_mapper import row_to_workspace
from ...models.workspace import Workspace, LaunchStatus
import logging

logger = logging.getLogger(__name__)


class WorkspacesStore(StoreBase):
    """Store for managing workspaces"""

    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace"""

        # Ensure default-user profile exists before we try to reference it as an owner
        if workspace.owner_user_id == "default-user":
            from backend.app.services.mindscape_store import MindscapeStore
            MindscapeStore().ensure_default_profile()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO workspaces (
                    id, owner_user_id, title, description, workspace_type, primary_project_id,
                    default_playbook_id, default_locale, mode, data_sources,
                    playbook_auto_execution_config, suggestion_history,
                    storage_base_path, artifacts_dir, uploads_dir, storage_config,
                    playbook_storage_config, cloud_remote_tools_config,
                    execution_mode, expected_artifacts, execution_priority,
                    project_assignment_mode, metadata, workspace_blueprint, launch_status, starter_kit_type,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    workspace.id,
                    workspace.owner_user_id,
                    workspace.title,
                    workspace.description,
                    (
                        workspace.workspace_type.value
                        if workspace.workspace_type
                        else "personal"
                    ),
                    workspace.primary_project_id,
                    workspace.default_playbook_id,
                    workspace.default_locale,
                    workspace.mode,
                    (
                        self.serialize_json(workspace.data_sources)
                        if workspace.data_sources
                        else None
                    ),
                    (
                        self.serialize_json(workspace.playbook_auto_execution_config)
                        if workspace.playbook_auto_execution_config
                        else None
                    ),
                    (
                        self.serialize_json(workspace.suggestion_history)
                        if workspace.suggestion_history
                        else None
                    ),
                    workspace.storage_base_path,
                    workspace.artifacts_dir,
                    workspace.uploads_dir,
                    (
                        self.serialize_json(workspace.storage_config)
                        if workspace.storage_config
                        else None
                    ),
                    (
                        self.serialize_json(workspace.playbook_storage_config)
                        if workspace.playbook_storage_config
                        else None
                    ),
                    (
                        self.serialize_json(
                            getattr(workspace, "cloud_remote_tools_config", None)
                        )
                        if getattr(workspace, "cloud_remote_tools_config", None)
                        else None
                    ),
                    workspace.execution_mode,
                    (
                        self.serialize_json(workspace.expected_artifacts)
                        if workspace.expected_artifacts
                        else None
                    ),
                    workspace.execution_priority,
                    (
                        workspace.project_assignment_mode.value
                        if workspace.project_assignment_mode
                        else "auto_silent"
                    ),
                    (
                        self.serialize_json(workspace.metadata)
                        if workspace.metadata
                        else None
                    ),
                    # Workspace launch enhancement fields
                    # Important: workspace_blueprint must use model_dump() to convert to dict before serialize (full-chain consistency)
                    # Important: launch_status is Enum, must use .value (store layer fixed conversion, frontend won't need to defend everywhere)
                    (
                        self.serialize_json(workspace.workspace_blueprint.model_dump())
                        if workspace.workspace_blueprint
                        else None
                    ),
                    (
                        workspace.launch_status.value
                        if workspace.launch_status
                        else LaunchStatus.PENDING.value
                    ),
                    workspace.starter_kit_type,
                    self.to_isoformat(workspace.created_at),
                    self.to_isoformat(workspace.updated_at),
                ),
            )
            conn.commit()
            return workspace

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_workspace(row)

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
        group_id: Optional[str] = None,
    ) -> List[Workspace]:
        """
        List workspaces for a user

        Args:
            owner_user_id: Owner user ID
            primary_project_id: Optional project filter
            limit: Maximum number of workspaces to return

        Returns:
            List of Workspace objects, ordered by updated_at DESC
        """
        if group_id:
            raise RuntimeError("workspace groups require the PostgreSQL topology authority")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM workspaces WHERE owner_user_id = ?"
            params = [owner_user_id]

            if primary_project_id:
                query += " AND primary_project_id = ?"
                params.append(primary_project_id)

            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_workspace(row) for row in rows]

    def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            workspace.updated_at = _utc_now()
            cursor.execute(
                """
                UPDATE workspaces SET
                    title = ?,
                    description = ?,
                    workspace_type = ?,
                    primary_project_id = ?,
                    default_playbook_id = ?,
                    default_locale = ?,
                    mode = ?,
                    data_sources = ?,
                    playbook_auto_execution_config = ?,
                    suggestion_history = ?,
                    storage_base_path = ?,
                    artifacts_dir = ?,
                    uploads_dir = ?,
                    storage_config = ?,
                    playbook_storage_config = ?,
                    cloud_remote_tools_config = ?,
                    execution_mode = ?,
                    expected_artifacts = ?,
                    execution_priority = ?,
                    project_assignment_mode = ?,
                    metadata = ?,
                    workspace_blueprint = ?,
                    launch_status = ?,
                    starter_kit_type = ?,
                    updated_at = ?
                WHERE id = ?
            """,
                (
                    workspace.title,
                    workspace.description,
                    (
                        workspace.workspace_type.value
                        if workspace.workspace_type
                        else "personal"
                    ),
                    workspace.primary_project_id,
                    workspace.default_playbook_id,
                    workspace.default_locale,
                    workspace.mode,
                    (
                        self.serialize_json(workspace.data_sources)
                        if workspace.data_sources
                        else None
                    ),
                    (
                        self.serialize_json(workspace.playbook_auto_execution_config)
                        if workspace.playbook_auto_execution_config
                        else None
                    ),
                    (
                        self.serialize_json(workspace.suggestion_history)
                        if workspace.suggestion_history
                        else None
                    ),
                    workspace.storage_base_path,
                    workspace.artifacts_dir,
                    workspace.uploads_dir,
                    (
                        self.serialize_json(workspace.storage_config)
                        if workspace.storage_config
                        else None
                    ),
                    (
                        self.serialize_json(workspace.playbook_storage_config)
                        if workspace.playbook_storage_config
                        else None
                    ),
                    (
                        self.serialize_json(
                            getattr(workspace, "cloud_remote_tools_config", None)
                        )
                        if getattr(workspace, "cloud_remote_tools_config", None)
                        else None
                    ),
                    workspace.execution_mode,
                    (
                        self.serialize_json(workspace.expected_artifacts)
                        if workspace.expected_artifacts
                        else None
                    ),
                    workspace.execution_priority,
                    (
                        workspace.project_assignment_mode.value
                        if workspace.project_assignment_mode
                        else "auto_silent"
                    ),
                    (
                        self.serialize_json(workspace.metadata)
                        if workspace.metadata
                        else None
                    ),
                    # Workspace launch enhancement fields
                    # Important: workspace_blueprint must use model_dump() to convert to dict before serialize (full-chain consistency)
                    # Important: launch_status is Enum, must use .value (store layer fixed conversion, frontend won't need to defend everywhere)
                    # Important: DB field is NOT NULL + default, theoretically won't be None, but keep defensive check
                    (
                        self.serialize_json(workspace.workspace_blueprint.model_dump())
                        if workspace.workspace_blueprint
                        else None
                    ),
                    (
                        workspace.launch_status.value
                        if workspace.launch_status
                        else LaunchStatus.PENDING.value
                    ),
                    workspace.starter_kit_type,
                    self.to_isoformat(workspace.updated_at),
                    workspace.id,
                ),
            )
            conn.commit()
            return workspace

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_workspace(self, row) -> Workspace:
        """Convert database row to Workspace"""
        return row_to_workspace(
            row,
            deserialize_json=self.deserialize_json,
            from_isoformat=self.from_isoformat,
        )
