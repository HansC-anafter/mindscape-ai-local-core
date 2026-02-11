"""
Task IR Store - Persistent storage for Task Intermediate Representations

Manages the persistence of Task IR objects, enabling cross-engine task state
sharing and long-running task resumption.
"""

import json
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, List, Optional
from backend.app.services.stores.base import StoreBase, StoreNotFoundError
from backend.app.models.task_ir import TaskIR, TaskIRUpdate, PhaseIR, ArtifactReference

logger = logging.getLogger(__name__)


class TaskIRStore(StoreBase):
    """
    Store for managing Task IR records

    Provides CRUD operations for Task IR objects and supports
    efficient querying for cross-engine interoperability.
    """

    def __init__(self, db_path: str):
        """
        Initialize Task IR store

        Args:
            db_path: Database file path
        """
        super().__init__(db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema"""
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Task IR table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_irs (
                    task_id TEXT PRIMARY KEY,
                    intent_instance_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    current_phase TEXT,
                    status TEXT NOT NULL,
                    phases TEXT NOT NULL,  -- JSON array of PhaseIR
                    artifacts TEXT NOT NULL,  -- JSON array of ArtifactReference
                    metadata TEXT NOT NULL,  -- JSON ExecutionMetadata
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_checkpoint_at TEXT
                )
            ''')

            # Indexes for efficient querying
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_irs_workspace ON task_irs(workspace_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_irs_intent ON task_irs(intent_instance_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_irs_status ON task_irs(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_irs_current_phase ON task_irs(current_phase)')

            logger.info("Task IR store schema initialized")

    def create_task_ir(self, task_ir: TaskIR) -> TaskIR:
        """
        Create a new Task IR record

        Args:
            task_ir: Task IR to create

        Returns:
            Created Task IR
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO task_irs (
                    task_id, intent_instance_id, workspace_id, actor_id,
                    current_phase, status, phases, artifacts, metadata,
                    created_at, updated_at, last_checkpoint_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task_ir.task_id,
                task_ir.intent_instance_id,
                task_ir.workspace_id,
                task_ir.actor_id,
                task_ir.current_phase,
                task_ir.status,
                self.serialize_json([p.dict() for p in task_ir.phases]),
                self.serialize_json([a.dict() for a in task_ir.artifacts]),
                self.serialize_json(task_ir.metadata.dict()),
                self.to_isoformat(task_ir.created_at),
                self.to_isoformat(task_ir.updated_at),
                self.to_isoformat(task_ir.last_checkpoint_at) if task_ir.last_checkpoint_at else None
            ))

            logger.info(f"Created Task IR: {task_ir.task_id} for workspace: {task_ir.workspace_id}")
            return task_ir

    def get_task_ir(self, task_id: str) -> Optional[TaskIR]:
        """
        Get Task IR by ID

        Args:
            task_id: Task ID

        Returns:
            Task IR or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM task_irs WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_task_ir(row)

    def update_task_ir(self, task_id: str, updates: TaskIRUpdate) -> bool:
        """
        Update Task IR with incremental changes

        Args:
            task_id: Task ID to update
            updates: Update operations

        Returns:
            True if updated, False if task not found
        """
        task_ir = self.get_task_ir(task_id)
        if not task_ir:
            return False

        # Apply phase updates
        for phase_id, phase_updates in updates.phase_updates.items():
            phase = task_ir.get_phase(phase_id)
            if phase:
                for key, value in phase_updates.items():
                    if hasattr(phase, key):
                        setattr(phase, key, value)

        # Add new artifacts
        for artifact in updates.new_artifacts:
            task_ir.add_artifact(artifact)

        # Update status and current phase
        if updates.status_update:
            task_ir.status = updates.status_update

        if updates.current_phase_update:
            task_ir.current_phase = updates.current_phase_update

        # Update timestamp
        task_ir.updated_at = _utc_now()
        if updates.phase_updates or updates.new_artifacts:
            task_ir.last_checkpoint_at = _utc_now()

        # Save to database
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE task_irs SET
                    current_phase = ?,
                    status = ?,
                    phases = ?,
                    artifacts = ?,
                    updated_at = ?,
                    last_checkpoint_at = ?
                WHERE task_id = ?
            ''', (
                task_ir.current_phase,
                task_ir.status,
                self.serialize_json([p.dict() for p in task_ir.phases]),
                self.serialize_json([a.dict() for a in task_ir.artifacts]),
                self.to_isoformat(task_ir.updated_at),
                self.to_isoformat(task_ir.last_checkpoint_at) if task_ir.last_checkpoint_at else None,
                task_id
            ))

        logger.info(f"Updated Task IR: {task_id} with {len(updates.phase_updates)} phase updates, {len(updates.new_artifacts)} new artifacts")
        return True

    def delete_task_ir(self, task_id: str) -> bool:
        """
        Delete Task IR

        Args:
            task_id: Task ID to delete

        Returns:
            True if deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM task_irs WHERE task_id = ?', (task_id,))
            deleted = cursor.rowcount > 0

            if deleted:
                logger.info(f"Deleted Task IR: {task_id}")

            return deleted

    def list_task_irs_by_workspace(self, workspace_id: str, limit: int = 50) -> List[TaskIR]:
        """
        List Task IRs for a workspace

        Args:
            workspace_id: Workspace ID
            limit: Maximum number of results

        Returns:
            List of Task IRs
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_irs
                WHERE workspace_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (workspace_id, limit))

            task_irs = []
            for row in cursor.fetchall():
                task_irs.append(self._row_to_task_ir(row))

            return task_irs

    def list_task_irs_by_intent(self, intent_instance_id: str, limit: int = 50) -> List[TaskIR]:
        """
        List Task IRs for an intent instance

        Args:
            intent_instance_id: Intent instance ID
            limit: Maximum number of results

        Returns:
            List of Task IRs
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_irs
                WHERE intent_instance_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (intent_instance_id, limit))

            task_irs = []
            for row in cursor.fetchall():
                task_irs.append(self._row_to_task_ir(row))

            return task_irs

    def list_task_irs_by_status(self, status: str, limit: int = 50) -> List[TaskIR]:
        """
        List Task IRs by status

        Args:
            status: Task status
            limit: Maximum number of results

        Returns:
            List of Task IRs
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_irs
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (status, limit))

            task_irs = []
            for row in cursor.fetchall():
                task_irs.append(self._row_to_task_ir(row))

            return task_irs

    def get_pending_tasks_for_engine(self, engine_type: str, limit: int = 10) -> List[TaskIR]:
        """
        Get pending tasks that can be executed by a specific engine type

        Args:
            engine_type: Engine type (playbook, skill, mcp, n8n)
            limit: Maximum number of results

        Returns:
            List of executable Task IRs
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_irs
                WHERE status IN ('pending', 'running')
                ORDER BY created_at ASC
                LIMIT ?
            ''', (limit * 2,))  # Get more to filter

            candidates = []
            for row in cursor.fetchall():
                task_ir = self._row_to_task_ir(row)

                # Check if task has executable phases for this engine
                executable_phases = [
                    p for p in task_ir.get_next_executable_phases()
                    if p.preferred_engine and p.preferred_engine.startswith(f"{engine_type}:")
                ]

                if executable_phases:
                    candidates.append((task_ir, executable_phases))

                if len(candidates) >= limit:
                    break

            return [task_ir for task_ir, _ in candidates[:limit]]

    def _row_to_task_ir(self, row: Dict[str, Any]) -> TaskIR:
        """
        Convert database row to Task IR

        Args:
            row: Database row

        Returns:
            Task IR instance
        """
        # Parse JSON fields
        phases_data = self.deserialize_json(row["phases"])
        artifacts_data = self.deserialize_json(row["artifacts"])
        metadata_data = self.deserialize_json(row["metadata"])

        # Convert to model instances
        phases = [PhaseIR(**phase_data) for phase_data in phases_data]
        artifacts = [ArtifactReference(**artifact_data) for artifact_data in artifacts_data]

        from backend.app.models.task_ir import ExecutionMetadata
        metadata = ExecutionMetadata(**metadata_data)

        return TaskIR(
            task_id=row["task_id"],
            intent_instance_id=row["intent_instance_id"],
            workspace_id=row["workspace_id"],
            actor_id=row["actor_id"],
            current_phase=row["current_phase"],
            status=row["status"],
            phases=phases,
            artifacts=artifacts,
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_checkpoint_at=datetime.fromisoformat(row["last_checkpoint_at"]) if row["last_checkpoint_at"] else None
        )

    def get_task_ir_stats(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Task IR statistics

        Args:
            workspace_id: Optional workspace filter

        Returns:
            Statistics dictionary
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if workspace_id:
                cursor.execute('''
                    SELECT
                        COUNT(*) as total_tasks,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                        COUNT(CASE WHEN status = 'running' THEN 1 END) as running_tasks,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_tasks,
                        AVG(JULIANDAY(updated_at) - JULIANDAY(created_at)) * 24 as avg_duration_hours
                    FROM task_irs
                    WHERE workspace_id = ?
                ''', (workspace_id,))
            else:
                cursor.execute('''
                    SELECT
                        COUNT(*) as total_tasks,
                        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                        COUNT(CASE WHEN status = 'running' THEN 1 END) as running_tasks,
                        COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_tasks,
                        AVG(JULIANDAY(updated_at) - JULIANDAY(created_at)) * 24 as avg_duration_hours
                    FROM task_irs
                ''')

            row = cursor.fetchone()
            if row:
                return {
                    "total_tasks": row[0],
                    "completed_tasks": row[1],
                    "running_tasks": row[2],
                    "failed_tasks": row[3],
                    "avg_duration_hours": row[4] if row[4] else 0
                }

            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "running_tasks": 0,
                "failed_tasks": 0,
                "avg_duration_hours": 0
            }
