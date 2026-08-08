"""Postgres adaptation of WorkspacesStore."""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import List, Optional, Dict, Any
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from .workspaces_projection import (
    compact_data_source_entry,
    row_to_workspace,
    row_to_workspace_summary,
)
from app.models.workspace import (
    Workspace,
    LaunchStatus,
)

logger = logging.getLogger(__name__)


class PostgresWorkspacesStore(PostgresStoreBase):
    """Postgres implementation of WorkspacesStore."""

    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO workspaces (
                    id, owner_user_id, title, description, workspace_type,
                    primary_project_id,
                    default_playbook_id, default_locale, mode, data_sources,
                    playbook_auto_execution_config, suggestion_history,
                    storage_base_path, artifacts_dir, uploads_dir, storage_config,
                    playbook_storage_config, cloud_remote_tools_config,
                    execution_mode, meeting_enabled,
                    expected_artifacts, execution_priority,
                    project_assignment_mode, metadata, workspace_blueprint, launch_status, starter_kit_type,
                    sandbox_config,
                    ttl_hours, expires_at, parent_workspace_id, visibility,
                    created_at, updated_at
                ) VALUES (
                    :id, :owner_user_id, :title, :description, :workspace_type,
                    :primary_project_id,
                    :default_playbook_id, :default_locale, :mode, :data_sources,
                    :playbook_auto_execution_config, :suggestion_history,
                    :storage_base_path, :artifacts_dir, :uploads_dir, :storage_config,
                    :playbook_storage_config, :cloud_remote_tools_config,
                    :execution_mode, :meeting_enabled,
                    :expected_artifacts, :execution_priority,
                    :project_assignment_mode, :metadata, :workspace_blueprint, :launch_status, :starter_kit_type,
                    :sandbox_config,
                    :ttl_hours, :expires_at, :parent_workspace_id, :visibility,
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
                "meeting_enabled": getattr(workspace, "meeting_enabled", False),
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
                "sandbox_config": (
                    self.serialize_json(workspace.sandbox_config)
                    if workspace.sandbox_config
                    else None
                ),
                "ttl_hours": getattr(workspace, "ttl_hours", None),
                "expires_at": getattr(workspace, "expires_at", None),
                "parent_workspace_id": getattr(workspace, "parent_workspace_id", None),
                "visibility": (
                    workspace.visibility.value
                    if getattr(workspace, "visibility", None)
                    else "private"
                ),
                "created_at": workspace.created_at,
                "updated_at": workspace.updated_at,
            }
            conn.execute(query, params)
            logger.info(f"Created workspace: {workspace.id}")
            return workspace

    def get_workspace_sync(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID (synchronous)."""
        with self.get_connection() as conn:
            query = text("SELECT * FROM workspaces WHERE id = :id")
            result = conn.execute(query, {"id": workspace_id})
            row = result.fetchone()
        if not row:
            return None
        return self._row_to_workspace(row)

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID (async wrapper for compatibility)."""
        import anyio
        return await anyio.to_thread.run_sync(self.get_workspace_sync, workspace_id)

    def get_workspace_summary_sync(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get workspace by ID without heavy data_sources and metadata columns."""
        with self.get_connection() as conn:
            query = text(
                """
                SELECT
                    id, owner_user_id, title, description, workspace_type,
                    primary_project_id,
                    default_playbook_id, default_locale, mode,
                    storage_base_path, artifacts_dir, uploads_dir, storage_config,
                    playbook_storage_config, playbook_auto_execution_config,
                    workspace_blueprint, execution_mode, meeting_enabled,
                    expected_artifacts, execution_priority, project_assignment_mode,
                    launch_status, starter_kit_type, ttl_hours, expires_at,
                    parent_workspace_id, visibility, created_at, updated_at
                FROM workspaces
                WHERE id = :id
                """
            )
            result = conn.execute(query, {"id": workspace_id})
            row = result.fetchone()
        if not row:
            return None
        return self._row_to_workspace_summary(row)

    async def get_workspace_summary(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Get workspace by ID without heavy data_sources and metadata columns."""
        import anyio
        return await anyio.to_thread.run_sync(self.get_workspace_summary_sync, workspace_id)

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
        group_id: Optional[str] = None,
    ) -> List[Workspace]:
        """List workspaces for a user."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM workspaces WHERE owner_user_id = :owner_user_id"
            params = {"owner_user_id": owner_user_id, "limit": limit}

            if primary_project_id:
                query_str += " AND primary_project_id = :primary_project_id"
                params["primary_project_id"] = primary_project_id

            if group_id:
                query_str += (
                    " AND EXISTS (SELECT 1 FROM workspace_group_memberships wgm "
                    "WHERE wgm.workspace_id = workspaces.id AND wgm.group_id = :group_id)"
                )
                params["group_id"] = group_id

            query_str += " ORDER BY updated_at DESC LIMIT :limit"

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
        return [self._row_to_workspace(row) for row in rows]

    def list_workspace_ids(
        self,
        owner_user_id: str,
        limit: int = 200,
    ) -> List[str]:
        """List only authorized workspace IDs for request-scope projection."""
        normalized_limit = max(1, min(200, int(limit or 200)))
        with self.get_connection() as conn:
            conn.execute(text("SET LOCAL statement_timeout = '10000ms'"))
            rows = conn.execute(
                text(
                    """
                    SELECT id
                    FROM workspaces
                    WHERE owner_user_id = :owner_user_id
                    ORDER BY updated_at DESC, id
                    LIMIT :limit
                    """
                ),
                {
                    "owner_user_id": owner_user_id,
                    "limit": normalized_limit,
                },
            ).fetchall()
        return [str(row.id) for row in rows]

    def list_workspace_summaries(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
        group_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List workspaces without heavy configuration columns."""
        with self.get_connection() as conn:
            query_str = """
                SELECT
                    id, owner_user_id, title, description, workspace_type,
                    primary_project_id,
                    default_playbook_id, default_locale, mode,
                    storage_base_path, artifacts_dir, uploads_dir, storage_config,
                    playbook_storage_config, playbook_auto_execution_config,
                    workspace_blueprint, execution_mode, meeting_enabled, expected_artifacts,
                    execution_priority, project_assignment_mode, launch_status,
                    starter_kit_type, ttl_hours, expires_at, parent_workspace_id,
                    visibility, created_at, updated_at
                FROM workspaces
                WHERE owner_user_id = :owner_user_id
            """
            params = {"owner_user_id": owner_user_id, "limit": limit}

            if primary_project_id:
                query_str += " AND primary_project_id = :primary_project_id"
                params["primary_project_id"] = primary_project_id

            if group_id:
                query_str += (
                    " AND EXISTS (SELECT 1 FROM workspace_group_memberships wgm "
                    "WHERE wgm.workspace_id = workspaces.id AND wgm.group_id = :group_id)"
                )
                params["group_id"] = group_id

            query_str += " ORDER BY updated_at DESC LIMIT :limit"

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
        return [self._row_to_workspace_summary(row) for row in rows]

    def update_workspace_sync(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace (synchronous)."""
        workspace.updated_at = _utc_now()
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
                    meeting_enabled = :meeting_enabled,
                    expected_artifacts = :expected_artifacts,
                    execution_priority = :execution_priority,
                    project_assignment_mode = :project_assignment_mode,
                    metadata = :metadata,
                    workspace_blueprint = :workspace_blueprint,
                    launch_status = :launch_status,
                    starter_kit_type = :starter_kit_type,
                    sandbox_config = :sandbox_config,
                    ttl_hours = :ttl_hours,
                    expires_at = :expires_at,
                    parent_workspace_id = :parent_workspace_id,
                    visibility = :visibility,
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
                "meeting_enabled": getattr(workspace, "meeting_enabled", False),
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
                "sandbox_config": (
                    self.serialize_json(workspace.sandbox_config)
                    if workspace.sandbox_config
                    else None
                ),
                "ttl_hours": getattr(workspace, "ttl_hours", None),
                "expires_at": getattr(workspace, "expires_at", None),
                "parent_workspace_id": getattr(workspace, "parent_workspace_id", None),
                "visibility": (
                    workspace.visibility.value
                    if getattr(workspace, "visibility", None)
                    else "private"
                ),
                "updated_at": workspace.updated_at,
                "id": workspace.id,
            }
            conn.execute(query, params)
            logger.info(f"Updated workspace: {workspace.id}")
            return workspace

    async def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace (async interface)."""
        import anyio
        return await anyio.to_thread.run_sync(self.update_workspace_sync, workspace)

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace."""
        with self.transaction() as conn:
            query = text("DELETE FROM workspaces WHERE id = :id")
            result = conn.execute(query, {"id": workspace_id})
            return result.rowcount > 0

    def _row_to_workspace_summary(self, row) -> Dict[str, Any]:
        return row_to_workspace_summary(row, deserialize_json=self.deserialize_json)

    def _row_to_workspace(self, row) -> Workspace:
        return row_to_workspace(row, deserialize_json=self.deserialize_json, logger=logger)

    def list_discoverable_workspaces(
        self,
        visibility: str = "discoverable",
        limit: int = 50,
    ) -> List[Workspace]:
        """List workspaces with the given visibility scope.

        Used by meeting engine discovery to build asset maps.
        """
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM workspaces "
                "WHERE visibility = :visibility "
                "ORDER BY updated_at DESC LIMIT :limit"
            )
            rows = conn.execute(query, {"visibility": visibility, "limit": limit}).fetchall()
        return [self._row_to_workspace(row) for row in rows]

    def merge_data_sources(
        self,
        workspace_id: str,
        pack_id: str,
        entry: Dict[str, Any],
    ) -> None:
        """Merge a single pack_id entry into workspace.data_sources.

        Performs a targeted UPDATE on only the data_sources column.
        Reads current value, merges the new entry, writes back.
        Called by task_result_landing on successful task completion.
        """
        with self.transaction() as conn:
            row = conn.execute(
                text("SELECT data_sources FROM workspaces WHERE id = :id"),
                {"id": workspace_id},
            ).fetchone()
            if not row:
                return

            raw_current = self.deserialize_json(row.data_sources) or {}
            current = {
                key: compact_data_source_entry(value)
                for key, value in raw_current.items()
                if isinstance(value, dict)
            }
            existing = current.get(pack_id, {})
            entry = compact_data_source_entry(entry)

            # Merge: increment total_runs, update last_run and last_result_summary
            existing["total_runs"] = existing.get("total_runs", 0) + 1
            existing["last_run"] = entry.get("last_run", _utc_now().isoformat())
            if entry.get("last_result_summary"):
                existing["last_result_summary"] = entry["last_result_summary"]
            if entry.get("produces"):
                existing["produces"] = entry["produces"]

            current[pack_id] = existing
            conn.execute(
                text(
                    "UPDATE workspaces SET data_sources = :ds, updated_at = :now "
                    "WHERE id = :id"
                ),
                {
                    "ds": self.serialize_json(current),
                    "now": _utc_now(),
                    "id": workspace_id,
                },
            )
