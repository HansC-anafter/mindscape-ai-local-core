"""
BackgroundRoutines store for managing background routine records

Background routines are long-running tasks that run on a schedule,
like cron jobs or daemons. Once enabled, they run automatically.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any, Tuple
from backend.app.services.stores.base import StoreBase, StoreNotFoundError
from ...models.workspace import BackgroundRoutine
from ...models.playbook import Playbook
from backend.app.services.playbook_tool_checker import PlaybookToolChecker, PlaybookReadinessStatus
from backend.app.services.tool_status_checker import ToolStatusChecker
from ...models.tool_connection import ToolConnectionStatus

logger = logging.getLogger(__name__)


class BackgroundRoutinesStore(StoreBase):
    """Store for managing background routine records"""

    def create_background_routine(self, routine: BackgroundRoutine) -> BackgroundRoutine:
        """
        Create a new background routine record

        Args:
            routine: BackgroundRoutine model instance

        Returns:
            Created background routine
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO background_routines (
                    id, workspace_id, playbook_code, enabled, config,
                    last_run_at, next_run_at, last_status,
                    readiness_status, tool_statuses, error_count, auto_paused,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                routine.id,
                routine.workspace_id,
                routine.playbook_code,
                1 if routine.enabled else 0,
                self.serialize_json(routine.config),
                self.to_isoformat(routine.last_run_at),
                self.to_isoformat(routine.next_run_at),
                routine.last_status,
                routine.readiness_status,
                self.serialize_json(routine.tool_statuses) if routine.tool_statuses else None,
                routine.error_count,
                1 if routine.auto_paused else 0,
                self.to_isoformat(routine.created_at),
                self.to_isoformat(routine.updated_at)
            ))
            logger.info(f"Created background routine: {routine.id} (workspace: {routine.workspace_id}, playbook: {routine.playbook_code})")
            return routine

    def get_background_routine(self, routine_id: str) -> Optional[BackgroundRoutine]:
        """
        Get background routine by ID

        Args:
            routine_id: Background routine ID

        Returns:
            BackgroundRoutine model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM background_routines WHERE id = ?', (routine_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_background_routine(row)

    def get_background_routine_by_playbook(
        self,
        workspace_id: str,
        playbook_code: str
    ) -> Optional[BackgroundRoutine]:
        """
        Get background routine by workspace and playbook code

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code

        Returns:
            BackgroundRoutine model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM background_routines WHERE workspace_id = ? AND playbook_code = ?',
                (workspace_id, playbook_code)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_background_routine(row)

    def list_background_routines_by_workspace(
        self,
        workspace_id: str,
        enabled_only: bool = False
    ) -> List[BackgroundRoutine]:
        """
        List background routines for a workspace

        Args:
            workspace_id: Workspace ID
            enabled_only: If True, only return enabled routines

        Returns:
            List of background routines, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM background_routines WHERE workspace_id = ?'
            params = [workspace_id]

            if enabled_only:
                query += ' AND enabled = 1'

            query += ' ORDER BY created_at DESC'

            cursor.execute(query, params)
            rows = cursor.fetchall()
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
        auto_paused: Optional[bool] = None
    ) -> BackgroundRoutine:
        """
        Update background routine

        Args:
            routine_id: Background routine ID
            enabled: Whether the routine is enabled
            config: Updated configuration (playbook-specific params)
            last_run_at: Last execution timestamp
            next_run_at: Next scheduled execution timestamp
            last_status: Last execution status
            readiness_status: Readiness status (ready/needs_setup/unsupported)
            tool_statuses: Status of required tools
            error_count: Consecutive error count
            auto_paused: Whether routine was auto-paused

        Returns:
            Updated background routine

        Raises:
            StoreNotFoundError: If routine not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Check if routine exists
            cursor.execute('SELECT * FROM background_routines WHERE id = ?', (routine_id,))
            row = cursor.fetchone()
            if not row:
                raise StoreNotFoundError(f"Background routine not found: {routine_id}")

            # Build update query
            updates = []
            params = []

            if enabled is not None:
                updates.append('enabled = ?')
                params.append(1 if enabled else 0)

            if config is not None:
                updates.append('config = ?')
                params.append(self.serialize_json(config))

            if last_run_at is not None:
                updates.append('last_run_at = ?')
                params.append(self.to_isoformat(last_run_at))

            if next_run_at is not None:
                updates.append('next_run_at = ?')
                params.append(self.to_isoformat(next_run_at))

            if last_status is not None:
                updates.append('last_status = ?')
                params.append(last_status)

            if readiness_status is not None:
                updates.append('readiness_status = ?')
                params.append(readiness_status)

            if tool_statuses is not None:
                updates.append('tool_statuses = ?')
                params.append(self.serialize_json(tool_statuses))

            if error_count is not None:
                updates.append('error_count = ?')
                params.append(error_count)

            if auto_paused is not None:
                updates.append('auto_paused = ?')
                params.append(1 if auto_paused else 0)

            if not updates:
                # No updates to make
                return self._row_to_background_routine(row)

            updates.append('updated_at = ?')
            params.append(self.to_isoformat(_utc_now()))
            params.append(routine_id)

            query = f'UPDATE background_routines SET {", ".join(updates)} WHERE id = ?'
            cursor.execute(query, params)

            logger.info(f"Updated background routine: {routine_id}")

            # Return updated routine
            cursor.execute('SELECT * FROM background_routines WHERE id = ?', (routine_id,))
            updated_row = cursor.fetchone()
            return self._row_to_background_routine(updated_row)

    def delete_background_routine(self, routine_id: str) -> bool:
        """
        Delete background routine

        Args:
            routine_id: Background routine ID

        Returns:
            True if deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM background_routines WHERE id = ?', (routine_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted background routine: {routine_id}")
            return deleted

    def _row_to_background_routine(self, row) -> BackgroundRoutine:
        """Convert database row to BackgroundRoutine model"""
        # sqlite3.Row doesn't support .get(), use try-except for optional fields
        last_run_at = None
        try:
            if row['last_run_at']:
                last_run_at = self.from_isoformat(row['last_run_at'])
        except (KeyError, TypeError):
            pass

        next_run_at = None
        try:
            if row['next_run_at']:
                next_run_at = self.from_isoformat(row['next_run_at'])
        except (KeyError, TypeError):
            pass

        last_status = None
        try:
            if row['last_status']:
                last_status = row['last_status']
        except (KeyError, TypeError):
            pass

        readiness_status = None
        try:
            if row['readiness_status']:
                readiness_status = row['readiness_status']
        except (KeyError, TypeError):
            pass

        tool_statuses = None
        try:
            if row['tool_statuses']:
                tool_statuses = self.deserialize_json(row['tool_statuses'])
        except (KeyError, TypeError):
            pass

        error_count = 0
        try:
            error_count = row['error_count']
        except (KeyError, TypeError):
            pass

        auto_paused = False
        try:
            auto_paused = bool(row['auto_paused'])
        except (KeyError, TypeError):
            pass

        return BackgroundRoutine(
            id=row['id'],
            workspace_id=row['workspace_id'],
            playbook_code=row['playbook_code'],
            enabled=bool(row['enabled']),
            config=self.deserialize_json(row['config']),
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            last_status=last_status,
            readiness_status=readiness_status,
            tool_statuses=tool_statuses,
            error_count=error_count,
            auto_paused=auto_paused,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

    def check_and_update_readiness(
        self,
        routine_id: str,
        playbook_tool_checker: PlaybookToolChecker,
        playbook: Playbook,
        profile_id: str
    ) -> Tuple[PlaybookReadinessStatus, Dict[str, ToolConnectionStatus]]:
        """
        Check and update background routine readiness status

        Args:
            routine_id: Background routine ID
            playbook_tool_checker: Playbook tool checker instance
            playbook: Playbook instance
            profile_id: Profile ID

        Returns:
            Tuple of (readiness_status, tool_statuses)

        Raises:
            StoreNotFoundError: If routine not found
        """
        readiness, tool_statuses, missing_required = playbook_tool_checker.check_playbook_tools(
            playbook=playbook,
            profile_id=profile_id
        )

        # Update routine with readiness status (as separate columns, not in config)
        self.update_background_routine(
            routine_id=routine_id,
            readiness_status=readiness.value,
            tool_statuses={
                tool_type: status.value
                for tool_type, status in tool_statuses.items()
            }
        )

        return readiness, tool_statuses

