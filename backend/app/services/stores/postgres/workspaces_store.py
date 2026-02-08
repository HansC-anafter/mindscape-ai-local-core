"""Postgres adaptation of WorkspacesStore."""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.workspace import (
    Workspace,
    LaunchStatus,
    WorkspaceType,
    ProjectAssignmentMode,
)
from app.models.workspace_blueprint import WorkspaceBlueprint

logger = logging.getLogger(__name__)


class PostgresWorkspacesStore(PostgresStoreBase):
    """Postgres implementation of WorkspacesStore."""

    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace."""
        with self.transaction() as conn:
            query = text(
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
                ) VALUES (
                    :id, :owner_user_id, :title, :description, :workspace_type, :primary_project_id,
                    :default_playbook_id, :default_locale, :mode, :data_sources,
                    :playbook_auto_execution_config, :suggestion_history,
                    :storage_base_path, :artifacts_dir, :uploads_dir, :storage_config,
                    :playbook_storage_config, :cloud_remote_tools_config,
                    :execution_mode, :expected_artifacts, :execution_priority,
                    :project_assignment_mode, :metadata, :workspace_blueprint, :launch_status, :starter_kit_type,
                    :created_at, :updated_at
                )
            """
            )
            params = {
                "id": workspace.id,
                "owner_user_id": workspace.owner_user_id,
                "title": workspace.title,
                "description": workspace.description,
                "workspace_type": (
                    workspace.workspace_type.value
                    if workspace.workspace_type
                    else "personal"
                ),
                "primary_project_id": workspace.primary_project_id,
                "default_playbook_id": workspace.default_playbook_id,
                "default_locale": workspace.default_locale,
                "mode": workspace.mode,
                "data_sources": (
                    self.serialize_json(workspace.data_sources)
                    if workspace.data_sources
                    else None
                ),
                "playbook_auto_execution_config": (
                    self.serialize_json(workspace.playbook_auto_execution_config)
                    if workspace.playbook_auto_execution_config
                    else None
                ),
                "suggestion_history": (
                    self.serialize_json(workspace.suggestion_history)
                    if workspace.suggestion_history
                    else None
                ),
                "storage_base_path": workspace.storage_base_path,
                "artifacts_dir": workspace.artifacts_dir,
                "uploads_dir": workspace.uploads_dir,
                "storage_config": (
                    self.serialize_json(workspace.storage_config)
                    if workspace.storage_config
                    else None
                ),
                "playbook_storage_config": (
                    self.serialize_json(workspace.playbook_storage_config)
                    if workspace.playbook_storage_config
                    else None
                ),
                "cloud_remote_tools_config": (
                    self.serialize_json(
                        getattr(workspace, "cloud_remote_tools_config", None)
                    )
                    if getattr(workspace, "cloud_remote_tools_config", None)
                    else None
                ),
                "execution_mode": workspace.execution_mode,
                "expected_artifacts": (
                    self.serialize_json(workspace.expected_artifacts)
                    if workspace.expected_artifacts
                    else None
                ),
                "execution_priority": workspace.execution_priority,
                "project_assignment_mode": (
                    workspace.project_assignment_mode.value
                    if workspace.project_assignment_mode
                    else "auto_silent"
                ),
                "metadata": (
                    self.serialize_json(workspace.metadata)
                    if workspace.metadata
                    else None
                ),
                "workspace_blueprint": (
                    self.serialize_json(workspace.workspace_blueprint.model_dump())
                    if workspace.workspace_blueprint
                    else None
                ),
                "launch_status": (
                    workspace.launch_status.value
                    if workspace.launch_status
                    else LaunchStatus.PENDING.value
                ),
                "starter_kit_type": workspace.starter_kit_type,
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at,
            }
            conn.execute(query, params)
            logger.info(f"Created workspace: {workspace.id}")
            return workspace

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID."""
        with self.get_connection() as conn:
            query = text("SELECT * FROM workspaces WHERE id = :id")
            result = conn.execute(query, {"id": workspace_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_workspace(row)

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Workspace]:
        """List workspaces for a user."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM workspaces WHERE owner_user_id = :owner_user_id"
            params = {"owner_user_id": owner_user_id, "limit": limit}

            if primary_project_id:
                query_str += " AND primary_project_id = :primary_project_id"
                params["primary_project_id"] = primary_project_id

            query_str += " ORDER BY updated_at DESC LIMIT :limit"

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
            return [self._row_to_workspace(row) for row in rows]

    async def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace."""
        workspace.updated_at = datetime.utcnow()
        with self.transaction() as conn:
            query = text(
                """
                UPDATE workspaces SET
                    title = :title,
                    description = :description,
                    workspace_type = :workspace_type,
                    primary_project_id = :primary_project_id,
                    default_playbook_id = :default_playbook_id,
                    default_locale = :default_locale,
                    mode = :mode,
                    data_sources = :data_sources,
                    playbook_auto_execution_config = :playbook_auto_execution_config,
                    suggestion_history = :suggestion_history,
                    storage_base_path = :storage_base_path,
                    artifacts_dir = :artifacts_dir,
                    uploads_dir = :uploads_dir,
                    storage_config = :storage_config,
                    playbook_storage_config = :playbook_storage_config,
                    cloud_remote_tools_config = :cloud_remote_tools_config,
                    execution_mode = :execution_mode,
                    expected_artifacts = :expected_artifacts,
                    execution_priority = :execution_priority,
                    project_assignment_mode = :project_assignment_mode,
                    metadata = :metadata,
                    workspace_blueprint = :workspace_blueprint,
                    launch_status = :launch_status,
                    starter_kit_type = :starter_kit_type,
                    preferred_agent = :preferred_agent,
                    sandbox_config = :sandbox_config,
                    doer_fallback_to_mindscape = :doer_fallback_to_mindscape,
                    updated_at = :updated_at
                WHERE id = :id
            """
            )
            params = {
                "title": workspace.title,
                "description": workspace.description,
                "workspace_type": (
                    workspace.workspace_type.value
                    if workspace.workspace_type
                    else "personal"
                ),
                "primary_project_id": workspace.primary_project_id,
                "default_playbook_id": workspace.default_playbook_id,
                "default_locale": workspace.default_locale,
                "mode": workspace.mode,
                "data_sources": (
                    self.serialize_json(workspace.data_sources)
                    if workspace.data_sources
                    else None
                ),
                "playbook_auto_execution_config": (
                    self.serialize_json(workspace.playbook_auto_execution_config)
                    if workspace.playbook_auto_execution_config
                    else None
                ),
                "suggestion_history": (
                    self.serialize_json(workspace.suggestion_history)
                    if workspace.suggestion_history
                    else None
                ),
                "storage_base_path": workspace.storage_base_path,
                "artifacts_dir": workspace.artifacts_dir,
                "uploads_dir": workspace.uploads_dir,
                "storage_config": (
                    self.serialize_json(workspace.storage_config)
                    if workspace.storage_config
                    else None
                ),
                "playbook_storage_config": (
                    self.serialize_json(workspace.playbook_storage_config)
                    if workspace.playbook_storage_config
                    else None
                ),
                "cloud_remote_tools_config": (
                    self.serialize_json(
                        getattr(workspace, "cloud_remote_tools_config", None)
                    )
                    if getattr(workspace, "cloud_remote_tools_config", None)
                    else None
                ),
                "execution_mode": workspace.execution_mode,
                "expected_artifacts": (
                    self.serialize_json(workspace.expected_artifacts)
                    if workspace.expected_artifacts
                    else None
                ),
                "execution_priority": workspace.execution_priority,
                "project_assignment_mode": (
                    workspace.project_assignment_mode.value
                    if workspace.project_assignment_mode
                    else "auto_silent"
                ),
                "metadata": (
                    self.serialize_json(workspace.metadata)
                    if workspace.metadata
                    else None
                ),
                "workspace_blueprint": (
                    self.serialize_json(workspace.workspace_blueprint.model_dump())
                    if workspace.workspace_blueprint
                    else None
                ),
                "launch_status": (
                    workspace.launch_status.value
                    if workspace.launch_status
                    else LaunchStatus.PENDING.value
                ),
                "starter_kit_type": workspace.starter_kit_type,
                "preferred_agent": workspace.preferred_agent,
                "sandbox_config": (
                    self.serialize_json(workspace.sandbox_config)
                    if workspace.sandbox_config
                    else None
                ),
                "doer_fallback_to_mindscape": getattr(
                    workspace, "doer_fallback_to_mindscape", True
                ),
                "updated_at": workspace.updated_at,
                "id": workspace.id,
            }
            conn.execute(query, params)
            logger.info(f"Updated workspace: {workspace.id}")
            return workspace

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace."""
        with self.transaction() as conn:
            query = text("DELETE FROM workspaces WHERE id = :id")
            result = conn.execute(query, {"id": workspace_id})
            return result.rowcount > 0

    def _row_to_workspace(self, row) -> Workspace:
        """Convert database row to Workspace."""

        # Enums / Enum-like fields
        try:
            workspace_type = WorkspaceType(row.workspace_type or "personal")
        except ValueError:
            workspace_type = WorkspaceType.PERSONAL

        try:
            project_assignment_mode = ProjectAssignmentMode(
                row.project_assignment_mode or "auto_silent"
            )
        except ValueError:
            project_assignment_mode = ProjectAssignmentMode.AUTO_SILENT

        try:
            launch_status = LaunchStatus(row.launch_status or "pending")
        except ValueError:
            launch_status = LaunchStatus.PENDING

        # Workspace Blueprint
        blueprint_data = self.deserialize_json(row.workspace_blueprint)
        workspace_blueprint = None
        if blueprint_data:
            try:
                workspace_blueprint = WorkspaceBlueprint.model_validate(blueprint_data)
            except Exception as e:
                logger.warning(
                    f"Failed to validate workspace_blueprint for {row.id}: {e}"
                )

        # Cloud remote tools config - handle as standard attr of Workspace if it exists
        # Model definition might not have it explicit in type hint but kwargs or meta?
        # Workspace model has it? I checked file, didn't see explicit field `cloud_remote_tools_config` in `Workspace` class definition in what I read?
        # Wait, lines 80-84 in update check `getattr(workspace, "cloud_remote_tools_config", None)`.
        # So it's dynamic or I missed it. I'll treat it as such or add to object if needed.
        # But `Workspace` init arguments must match.
        # If I look at `Workspace` fields again... I don't see `cloud_remote_tools_config` in `Workspace` definition in Step 1010.
        # But `WorkspacesStore` SQL includes it?
        # Step 1011 line 29: `cloud_remote_tools_config` in INSERT.
        # Step 1011 line 78 calls `getattr`.
        # So it seems valid to support it?
        # However, `Workspace(...)` constructor call in Step 1011 `_row_to_workspace` does NOT pass `cloud_remote_tools_config`.
        # So I will NOT pass it to constructor either. I will just rely on `metadata` if it's there?
        # No, the store writes it to a column. But if Model doesn't have it, where does it go?
        # It gets lost on read?
        # I'll check `_row_to_workspace` in Step 1011 again.
        # It does NOT extract `cloud_remote_tools_config` from row.
        # So it seems `cloud_remote_tools_config` column is write-only or I missed something?
        # Or maybe it's new and not fully wired?
        # I will match `_row_to_workspace` from Step 1011 which ignores it on read.

        return Workspace(
            id=row.id,
            owner_user_id=row.owner_user_id,
            title=row.title,
            description=row.description,
            workspace_type=workspace_type,
            primary_project_id=row.primary_project_id,
            default_playbook_id=row.default_playbook_id,
            default_locale=row.default_locale,
            mode=row.mode,
            data_sources=self.deserialize_json(row.data_sources),
            playbook_auto_execution_config=self.deserialize_json(
                row.playbook_auto_execution_config
            ),
            suggestion_history=self.deserialize_json(
                row.suggestion_history, default=[]
            ),
            storage_base_path=row.storage_base_path,
            artifacts_dir=row.artifacts_dir,
            uploads_dir=row.uploads_dir,
            storage_config=self.deserialize_json(row.storage_config),
            playbook_storage_config=self.deserialize_json(row.playbook_storage_config),
            execution_mode=row.execution_mode or "qa",
            expected_artifacts=self.deserialize_json(
                row.expected_artifacts, default=[]
            ),
            execution_priority=row.execution_priority or "medium",
            project_assignment_mode=project_assignment_mode,
            metadata=self.deserialize_json(row.metadata, {}),
            workspace_blueprint=workspace_blueprint,
            launch_status=launch_status,
            starter_kit_type=row.starter_kit_type,
            preferred_agent=getattr(row, "preferred_agent", None),
            sandbox_config=self.deserialize_json(getattr(row, "sandbox_config", None)),
            doer_fallback_to_mindscape=getattr(row, "doer_fallback_to_mindscape", True),
            created_at=row.created_at,
            updated_at=row.updated_at,
            # cloud_remote_tools_config is ignored as per reference implementation
        )
