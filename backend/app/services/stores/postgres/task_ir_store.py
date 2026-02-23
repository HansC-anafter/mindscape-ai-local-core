"""
PostgreSQL implementation of TaskIRStore.

Replaces the SQLite-based TaskIRStore with PostgresStoreBase.
Uses native JSONB for phases, artifacts, and metadata columns.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.task_ir import (
    ArtifactReference,
    ExecutionMetadata,
    PhaseIR,
    TaskIR,
    TaskIRUpdate,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresTaskIRStore(PostgresStoreBase):
    """PostgreSQL implementation of TaskIR persistence."""

    def create_task_ir(self, task_ir: TaskIR) -> TaskIR:
        """Create a new Task IR record."""
        query = text(
            """
            INSERT INTO task_irs (
                task_id, intent_instance_id, workspace_id, actor_id,
                current_phase, status, phases, artifacts, metadata,
                created_at, updated_at, last_checkpoint_at
            ) VALUES (
                :task_id, :intent_instance_id, :workspace_id, :actor_id,
                :current_phase, :status, :phases, :artifacts, :metadata,
                :created_at, :updated_at, :last_checkpoint_at
            )
        """
        )
        params = self._task_ir_to_params(task_ir)
        with self.transaction() as conn:
            conn.execute(query, params)
        logger.info(
            "Created TaskIR %s for workspace %s", task_ir.task_id, task_ir.workspace_id
        )
        return task_ir

    def get_task_ir(self, task_id: str) -> Optional[TaskIR]:
        """Get Task IR by ID."""
        query = text("SELECT * FROM task_irs WHERE task_id = :task_id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"task_id": task_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_task_ir(row)

    def update_task_ir(self, task_id: str, updates: TaskIRUpdate) -> bool:
        """Update Task IR with incremental changes."""
        task_ir = self.get_task_ir(task_id)
        if not task_ir:
            return False

        for phase_id, phase_updates in updates.phase_updates.items():
            phase = task_ir.get_phase(phase_id)
            if phase:
                for key, value in phase_updates.items():
                    if hasattr(phase, key):
                        setattr(phase, key, value)

        for artifact in updates.new_artifacts:
            task_ir.add_artifact(artifact)

        if updates.status_update:
            task_ir.status = updates.status_update
        if updates.current_phase_update:
            task_ir.current_phase = updates.current_phase_update

        task_ir.updated_at = _utc_now()
        if updates.phase_updates or updates.new_artifacts:
            task_ir.last_checkpoint_at = _utc_now()

        query = text(
            """
            UPDATE task_irs SET
                current_phase = :current_phase,
                status = :status,
                phases = :phases,
                artifacts = :artifacts,
                updated_at = :updated_at,
                last_checkpoint_at = :last_checkpoint_at
            WHERE task_id = :task_id
        """
        )
        params = {
            "current_phase": task_ir.current_phase,
            "status": task_ir.status,
            "phases": self.serialize_json([p.model_dump() for p in task_ir.phases]),
            "artifacts": self.serialize_json(
                [a.model_dump() for a in task_ir.artifacts]
            ),
            "updated_at": task_ir.updated_at,
            "last_checkpoint_at": task_ir.last_checkpoint_at,
            "task_id": task_id,
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        logger.info("Updated TaskIR %s", task_id)
        return True

    def replace_task_ir(self, task_ir) -> bool:
        """Replace an existing TaskIR atomically (DELETE + INSERT).

        If the task_id does not exist, performs a plain INSERT.
        Runs inside a single transaction.

        Returns:
            True if an existing row was replaced, False if fresh insert.
        """
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM task_irs WHERE task_id = :task_id"),
                {"task_id": task_ir.task_id},
            )
            replaced = result.rowcount > 0

            query = text(
                """
                INSERT INTO task_irs (
                    task_id, intent_instance_id, workspace_id, actor_id,
                    current_phase, status, phases, artifacts, metadata,
                    created_at, updated_at, last_checkpoint_at
                ) VALUES (
                    :task_id, :intent_instance_id, :workspace_id, :actor_id,
                    :current_phase, :status, :phases, :artifacts, :metadata,
                    :created_at, :updated_at, :last_checkpoint_at
                )
            """
            )
            conn.execute(query, self._task_ir_to_params(task_ir))

        logger.info("Replaced TaskIR %s (was_existing=%s)", task_ir.task_id, replaced)
        return replaced

    def delete_task_ir(self, task_id: str) -> bool:
        """Delete Task IR."""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM task_irs WHERE task_id = :task_id"),
                {"task_id": task_id},
            )
            deleted = result.rowcount > 0
        if deleted:
            logger.info("Deleted TaskIR %s", task_id)
        return deleted

    def list_task_irs_by_workspace(
        self, workspace_id: str, limit: int = 50
    ) -> List[TaskIR]:
        """List Task IRs for a workspace."""
        query = text(
            """
            SELECT * FROM task_irs
            WHERE workspace_id = :workspace_id
            ORDER BY updated_at DESC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"workspace_id": workspace_id, "limit": limit})
            return [self._row_to_task_ir(row) for row in result.fetchall()]

    def list_task_irs_by_intent(
        self, intent_instance_id: str, limit: int = 50
    ) -> List[TaskIR]:
        """List Task IRs for an intent instance."""
        query = text(
            """
            SELECT * FROM task_irs
            WHERE intent_instance_id = :intent_instance_id
            ORDER BY updated_at DESC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query, {"intent_instance_id": intent_instance_id, "limit": limit}
            )
            return [self._row_to_task_ir(row) for row in result.fetchall()]

    def list_task_irs_by_status(self, status: str, limit: int = 50) -> List[TaskIR]:
        """List Task IRs by status."""
        query = text(
            """
            SELECT * FROM task_irs
            WHERE status = :status
            ORDER BY updated_at DESC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"status": status, "limit": limit})
            return [self._row_to_task_ir(row) for row in result.fetchall()]

    def get_pending_tasks_for_engine(
        self, engine_type: str, limit: int = 10
    ) -> List[TaskIR]:
        """Get pending tasks executable by a specific engine type."""
        query = text(
            """
            SELECT * FROM task_irs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at ASC
            LIMIT :fetch_limit
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"fetch_limit": limit * 2})
            candidates = []
            for row in result.fetchall():
                task_ir = self._row_to_task_ir(row)
                executable_phases = [
                    p
                    for p in task_ir.get_next_executable_phases()
                    if p.preferred_engine
                    and p.preferred_engine.startswith(f"{engine_type}:")
                ]
                if executable_phases:
                    candidates.append(task_ir)
                if len(candidates) >= limit:
                    break
            return candidates

    def get_task_ir_stats(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Get Task IR statistics."""
        if workspace_id:
            query = text(
                """
                SELECT
                    COUNT(*) as total_tasks,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                    COUNT(CASE WHEN status = 'running' THEN 1 END) as running_tasks,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_tasks,
                    AVG(EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600) as avg_duration_hours
                FROM task_irs
                WHERE workspace_id = :workspace_id
            """
            )
            params = {"workspace_id": workspace_id}
        else:
            query = text(
                """
                SELECT
                    COUNT(*) as total_tasks,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_tasks,
                    COUNT(CASE WHEN status = 'running' THEN 1 END) as running_tasks,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_tasks,
                    AVG(EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600) as avg_duration_hours
                FROM task_irs
            """
            )
            params = {}

        with self.get_connection() as conn:
            result = conn.execute(query, params)
            row = result.fetchone()
            if row:
                return {
                    "total_tasks": row[0] or 0,
                    "completed_tasks": row[1] or 0,
                    "running_tasks": row[2] or 0,
                    "failed_tasks": row[3] or 0,
                    "avg_duration_hours": row[4] or 0,
                }
        return {
            "total_tasks": 0,
            "completed_tasks": 0,
            "running_tasks": 0,
            "failed_tasks": 0,
            "avg_duration_hours": 0,
        }

    # -- Internal helpers ---------------------------------------------------

    def _task_ir_to_params(self, task_ir) -> Dict[str, Any]:
        """Convert TaskIR to query parameters."""
        return {
            "task_id": task_ir.task_id,
            "intent_instance_id": task_ir.intent_instance_id,
            "workspace_id": task_ir.workspace_id,
            "actor_id": task_ir.actor_id,
            "current_phase": task_ir.current_phase,
            "status": task_ir.status,
            "phases": self.serialize_json([p.model_dump() for p in task_ir.phases]),
            "artifacts": self.serialize_json(
                [a.model_dump() for a in task_ir.artifacts]
            ),
            "metadata": self.serialize_json(task_ir.metadata.model_dump()),
            "created_at": task_ir.created_at,
            "updated_at": task_ir.updated_at,
            "last_checkpoint_at": task_ir.last_checkpoint_at,
        }

    def _row_to_task_ir(self, row) -> TaskIR:
        """Convert database row to TaskIR."""
        phases_data = self.deserialize_json(getattr(row, "phases", "[]"), default=[])
        artifacts_data = self.deserialize_json(
            getattr(row, "artifacts", "[]"), default=[]
        )
        metadata_data = self.deserialize_json(
            getattr(row, "metadata", "{}"), default={}
        )

        phases = [PhaseIR(**p) for p in phases_data]
        artifacts = [ArtifactReference(**a) for a in artifacts_data]
        metadata = ExecutionMetadata(**metadata_data)

        return TaskIR(
            task_id=row.task_id,
            intent_instance_id=row.intent_instance_id,
            workspace_id=row.workspace_id,
            actor_id=row.actor_id,
            current_phase=row.current_phase,
            status=row.status,
            phases=phases,
            artifacts=artifacts,
            metadata=metadata,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_checkpoint_at=row.last_checkpoint_at,
        )
