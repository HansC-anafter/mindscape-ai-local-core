"""PostgreSQL implementation of BackgroundRoutinesStore."""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.workspace import BackgroundRoutine
from backend.app.models.playbook import Playbook
from backend.app.services.playbook_tool_checker import (
    PlaybookToolChecker,
    PlaybookReadinessStatus,
)
from backend.app.models.tool_connection import ToolConnectionStatus

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresBackgroundRoutinesStore(PostgresStoreBase):
    """Postgres implementation of BackgroundRoutinesStore."""

    def create_background_routine(
        self, routine: BackgroundRoutine
    ) -> BackgroundRoutine:
        """Create a new background routine record."""
        query = text(
            """
            INSERT INTO background_routines (
                id, workspace_id, playbook_code, enabled, config,
                last_run_at, next_run_at, last_status,
                readiness_status, tool_statuses, error_count, auto_paused,
                created_at, updated_at
            ) VALUES (
                :id, :workspace_id, :playbook_code, :enabled, :config,
                :last_run_at, :next_run_at, :last_status,
                :readiness_status, :tool_statuses, :error_count, :auto_paused,
                :created_at, :updated_at
            )
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": routine.id,
                    "workspace_id": routine.workspace_id,
                    "playbook_code": routine.playbook_code,
                    "enabled": routine.enabled,
                    "config": self.serialize_json(routine.config),
                    "last_run_at": routine.last_run_at,
                    "next_run_at": routine.next_run_at,
                    "last_status": routine.last_status,
                    "readiness_status": routine.readiness_status,
                    "tool_statuses": (
                        self.serialize_json(routine.tool_statuses)
                        if routine.tool_statuses
                        else None
                    ),
                    "error_count": routine.error_count,
                    "auto_paused": routine.auto_paused,
                    "created_at": routine.created_at,
                    "updated_at": routine.updated_at,
                },
            )
        logger.info(
            f"Created background routine: {routine.id} "
            f"(workspace: {routine.workspace_id}, playbook: {routine.playbook_code})"
        )
        return routine

    def get_background_routine(self, routine_id: str) -> Optional[BackgroundRoutine]:
        """Get background routine by ID."""
        query = text("SELECT * FROM background_routines WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": routine_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_background_routine(row)

    def get_background_routine_by_playbook(
        self, workspace_id: str, playbook_code: str
    ) -> Optional[BackgroundRoutine]:
        """Get background routine by workspace and playbook code."""
        query = text(
            "SELECT * FROM background_routines "
            "WHERE workspace_id = :workspace_id AND playbook_code = :playbook_code"
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "workspace_id": workspace_id,
                    "playbook_code": playbook_code,
                },
            )
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_background_routine(row)

    def list_background_routines_by_workspace(
        self, workspace_id: str, enabled_only: bool = False
    ) -> List[BackgroundRoutine]:
        """List background routines for a workspace."""
        base_query = (
            "SELECT * FROM background_routines WHERE workspace_id = :workspace_id"
        )
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if enabled_only:
            base_query += " AND enabled = true"

        base_query += " ORDER BY created_at DESC"

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_background_routine(row) for row in rows]

    def update_background_routine(
        self,
        routine_id: str,
        enabled: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None,
        last_run_at: Optional[datetime] = None,
        next_run_at: Optional[datetime] = None,
        last_status: Optional[str] = None,
        readiness_status: Optional[str] = None,
        tool_statuses: Optional[Dict[str, str]] = None,
        error_count: Optional[int] = None,
        auto_paused: Optional[bool] = None,
    ) -> BackgroundRoutine:
        """Update background routine."""
        # Check existence
        existing = self.get_background_routine(routine_id)
        if not existing:
            from backend.app.services.stores.base import StoreNotFoundError

            raise StoreNotFoundError(f"Background routine not found: {routine_id}")

        updates = []
        params: Dict[str, Any] = {"id": routine_id}

        if enabled is not None:
            updates.append("enabled = :enabled")
            params["enabled"] = enabled

        if config is not None:
            updates.append("config = :config")
            params["config"] = self.serialize_json(config)

        if last_run_at is not None:
            updates.append("last_run_at = :last_run_at")
            params["last_run_at"] = last_run_at

        if next_run_at is not None:
            updates.append("next_run_at = :next_run_at")
            params["next_run_at"] = next_run_at

        if last_status is not None:
            updates.append("last_status = :last_status")
            params["last_status"] = last_status

        if readiness_status is not None:
            updates.append("readiness_status = :readiness_status")
            params["readiness_status"] = readiness_status

        if tool_statuses is not None:
            updates.append("tool_statuses = :tool_statuses")
            params["tool_statuses"] = self.serialize_json(tool_statuses)

        if error_count is not None:
            updates.append("error_count = :error_count")
            params["error_count"] = error_count

        if auto_paused is not None:
            updates.append("auto_paused = :auto_paused")
            params["auto_paused"] = auto_paused

        if not updates:
            return existing

        updates.append("updated_at = :updated_at")
        params["updated_at"] = _utc_now()

        query = text(
            f"UPDATE background_routines SET {', '.join(updates)} WHERE id = :id"
        )
        with self.transaction() as conn:
            conn.execute(query, params)

        logger.info(f"Updated background routine: {routine_id}")
        return self.get_background_routine(routine_id)

    def delete_background_routine(self, routine_id: str) -> bool:
        """Delete background routine."""
        query = text("DELETE FROM background_routines WHERE id = :id")
        with self.transaction() as conn:
            result = conn.execute(query, {"id": routine_id})
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"Deleted background routine: {routine_id}")
            return deleted

    def _row_to_background_routine(self, row) -> BackgroundRoutine:
        """Convert database row to BackgroundRoutine model."""
        return BackgroundRoutine(
            id=row.id,
            workspace_id=row.workspace_id,
            playbook_code=row.playbook_code,
            enabled=bool(row.enabled),
            config=self.deserialize_json(row.config, default={}),
            last_run_at=row.last_run_at if row.last_run_at else None,
            next_run_at=row.next_run_at if row.next_run_at else None,
            last_status=row.last_status if row.last_status else None,
            readiness_status=row.readiness_status if row.readiness_status else None,
            tool_statuses=(
                self.deserialize_json(row.tool_statuses) if row.tool_statuses else None
            ),
            error_count=row.error_count if row.error_count else 0,
            auto_paused=bool(row.auto_paused) if row.auto_paused else False,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def check_and_update_readiness(
        self,
        routine_id: str,
        playbook_tool_checker: PlaybookToolChecker,
        playbook: Playbook,
        profile_id: str,
    ) -> Tuple[PlaybookReadinessStatus, Dict[str, ToolConnectionStatus]]:
        """Check and update background routine readiness status."""
        readiness, tool_statuses, missing_required = (
            playbook_tool_checker.check_playbook_tools(
                playbook=playbook,
                profile_id=profile_id,
            )
        )

        self.update_background_routine(
            routine_id=routine_id,
            readiness_status=readiness.value,
            tool_statuses={
                tool_type: status.value for tool_type, status in tool_statuses.items()
            },
        )

        return readiness, tool_statuses
