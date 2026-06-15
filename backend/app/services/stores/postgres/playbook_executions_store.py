from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

from .remaining_store_utils import _utc_now

logger = logging.getLogger(__name__)


# =================================================================================
# Playbook Executions Store
# =================================================================================
class PostgresPlaybookExecutionsStore(PostgresStoreBase):
    """Postgres implementation of PlaybookExecutionsStore."""

    def create_execution(self, execution: PlaybookExecution) -> PlaybookExecution:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO playbook_executions (
                    id, workspace_id, playbook_code, intent_instance_id, thread_id,
                    status, phase, last_checkpoint, progress_log_path,
                    feature_list_path, metadata, created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :playbook_code, :intent_instance_id, :thread_id,
                    :status, :phase, :last_checkpoint, :progress_log_path,
                    :feature_list_path, :metadata, :created_at, :updated_at
                )
            """
            )
            params = {
                "id": execution.id,
                "workspace_id": execution.workspace_id,
                "playbook_code": execution.playbook_code,
                "intent_instance_id": execution.intent_instance_id,
                "thread_id": execution.thread_id,
                "status": execution.status,
                "phase": execution.phase,
                "last_checkpoint": execution.last_checkpoint,
                "progress_log_path": execution.progress_log_path,
                "feature_list_path": execution.feature_list_path,
                "metadata": (
                    self.serialize_json(execution.metadata)
                    if execution.metadata
                    else None
                ),
                "created_at": execution.created_at,
                "updated_at": execution.updated_at,
            }
            conn.execute(query, params)
            logger.info(f"Created playbook execution: {execution.id}")
            return execution

    def get_execution(self, execution_id: str) -> Optional[PlaybookExecution]:
        with self.get_connection() as conn:
            query = text("SELECT * FROM playbook_executions WHERE id = :id")
            row = conn.execute(query, {"id": execution_id}).fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    def update_checkpoint(
        self, execution_id: str, checkpoint_data: str, phase: Optional[str] = None
    ) -> bool:
        with self.transaction() as conn:
            update_fields = [
                "last_checkpoint = :last_checkpoint",
                "updated_at = :updated_at",
            ]
            params = {
                "last_checkpoint": checkpoint_data,
                "updated_at": _utc_now(),
                "id": execution_id,
            }
            if phase is not None:
                update_fields.append("phase = :phase")
                params["phase"] = phase

            query = text(
                f"UPDATE playbook_executions SET {', '.join(update_fields)} WHERE id = :id"
            )
            result = conn.execute(query, params)
            return result.rowcount > 0

    def add_phase_summary(
        self, execution_id: str, phase: str, summary_data: Dict[str, Any]
    ) -> bool:
        # Just updates timestamp as per original implementation
        with self.transaction() as conn:
            query = text(
                "UPDATE playbook_executions SET updated_at = :updated_at WHERE id = :id"
            )
            result = conn.execute(
                query, {"updated_at": _utc_now(), "id": execution_id}
            )
            return result.rowcount > 0

    def list_executions_by_workspace(
        self, workspace_id: str, limit: int = 50
    ) -> List[PlaybookExecution]:
        with self.get_connection() as conn:
            query = text(
                """
                SELECT * FROM playbook_executions
                WHERE workspace_id = :workspace_id
                ORDER BY created_at DESC
                LIMIT :limit
            """
            )
            rows = conn.execute(
                query, {"workspace_id": workspace_id, "limit": limit}
            ).fetchall()
            return [self._row_to_execution(row) for row in rows]

    def list_executions_by_intent(
        self, intent_instance_id: str, limit: int = 50
    ) -> List[PlaybookExecution]:
        with self.get_connection() as conn:
            query = text(
                """
                SELECT * FROM playbook_executions
                WHERE intent_instance_id = :intent_instance_id
                ORDER BY created_at DESC
                LIMIT :limit
            """
            )
            rows = conn.execute(
                query, {"intent_instance_id": intent_instance_id, "limit": limit}
            ).fetchall()
            return [self._row_to_execution(row) for row in rows]

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: Optional[int] = 20
    ) -> List[PlaybookExecution]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM playbook_executions WHERE workspace_id = :workspace_id AND thread_id = :thread_id ORDER BY created_at DESC"
            params = {"workspace_id": workspace_id, "thread_id": thread_id}
            if limit:
                query_str += " LIMIT :limit"
                params["limit"] = limit
            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_execution(row) for row in rows]

    def update_execution_status(
        self, execution_id: str, status: str, phase: Optional[str] = None
    ) -> bool:
        with self.transaction() as conn:
            update_fields = ["status = :status", "updated_at = :updated_at"]
            params = {
                "status": status,
                "updated_at": _utc_now(),
                "id": execution_id,
            }
            if phase is not None:
                update_fields.append("phase = :phase")
                params["phase"] = phase

            query = text(
                f"UPDATE playbook_executions SET {', '.join(update_fields)} WHERE id = :id"
            )
            result = conn.execute(query, params)
            return result.rowcount > 0

    def update_execution_metadata(
        self, execution_id: str, metadata: Dict[str, Any]
    ) -> bool:
        current = self.get_execution(execution_id)
        if not current:
            return False

        merged_metadata = current.metadata or {}
        merged_metadata.update(metadata)

        with self.transaction() as conn:
            query = text(
                "UPDATE playbook_executions SET metadata = :metadata, updated_at = :updated_at WHERE id = :id"
            )
            result = conn.execute(
                query,
                {
                    "metadata": self.serialize_json(merged_metadata),
                    "updated_at": _utc_now(),
                    "id": execution_id,
                },
            )
            return result.rowcount > 0

    def get_playbook_workspace_stats(self, playbook_code: str) -> Dict[str, Any]:
        # Reuse base logic but with postgres query
        with self.get_connection() as conn:
            query = text(
                """
                SELECT workspace_id, status, created_at, updated_at
                FROM playbook_executions
                WHERE playbook_code = :playbook_code
                ORDER BY created_at DESC
            """
            )
            rows = conn.execute(query, {"playbook_code": playbook_code}).fetchall()

            # Logic is identical to original store, just adapting row access
            workspace_stats_map = {}
            for row in rows:
                workspace_id = row.workspace_id
                status = row.status
                created_at = row.created_at  # Already datetime

                if workspace_id not in workspace_stats_map:
                    workspace_stats_map[workspace_id] = {
                        "workspace_id": workspace_id,
                        "execution_count": 0,
                        "success_count": 0,
                        "failed_count": 0,
                        "running_count": 0,
                        "last_executed_at": None,
                    }

                stats = workspace_stats_map[workspace_id]
                stats["execution_count"] += 1

                if status in ["completed", "success"]:
                    stats["success_count"] += 1
                elif status in ["failed", "error"]:
                    stats["failed_count"] += 1
                elif status in ["running", "pending", "initializing"]:
                    stats["running_count"] += 1

                if created_at:
                    if (
                        stats["last_executed_at"] is None
                        or created_at.isoformat() > stats["last_executed_at"]
                    ):
                        stats["last_executed_at"] = created_at.isoformat()

            workspace_stats = list(workspace_stats_map.values())
            workspace_stats.sort(key=lambda x: x["execution_count"], reverse=True)

            return {
                "playbook_code": playbook_code,
                "total_executions": len(rows),
                "total_workspaces": len(workspace_stats),
                "workspace_stats": workspace_stats,
            }

    def _row_to_execution(self, row) -> PlaybookExecution:
        return PlaybookExecution(
            id=row.id,
            workspace_id=row.workspace_id,
            playbook_code=row.playbook_code,
            intent_instance_id=row.intent_instance_id,
            thread_id=row.thread_id,
            status=row.status,
            phase=row.phase,
            last_checkpoint=row.last_checkpoint,
            progress_log_path=row.progress_log_path,
            feature_list_path=row.feature_list_path,
            metadata=self.deserialize_json(row.metadata) if row.metadata else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
