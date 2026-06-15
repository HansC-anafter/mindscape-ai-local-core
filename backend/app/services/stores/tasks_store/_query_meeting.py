
"""Meeting and running-state read-only query methods for TasksStore."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


class TasksStoreMeetingQueryMixin:
    """Meeting-session and running/frontier query methods."""

    def list_tasks_by_meeting_session(
        self,
        session_id: Optional[str] = None,
        limit: int = 200,
        workspace_id: Optional[str] = None,
        meeting_session_id: Optional[str] = None,
    ) -> List[Task]:
        """List tasks spawned by a specific meeting session.

        Checks the meeting_session_id column first, falling back to
        execution_context/params JSON columns for backward compatibility.
        """
        effective_session_id = meeting_session_id or session_id
        if not effective_session_id:
            return []

        normalized_limit = max(1, min(int(limit or 200), 500))
        lookup_clauses = [
            "meeting_session_id = :sid",
            "execution_context->>'meeting_session_id' = :sid",
            "execution_context->>'thread_id' = :sid",
            "params->>'meeting_session_id' = :sid",
            "params->>'thread_id' = :sid",
        ]
        base_params: Dict[str, Any] = {"sid": effective_session_id}
        if workspace_id:
            base_params["workspace_id"] = workspace_id

        tasks: List[Task] = []
        seen_ids: set[str] = set()
        with self.get_connection() as conn:
            try:
                conn.execute(text("SET statement_timeout TO '1500ms'"))
            except Exception:
                logger.debug("Unable to set statement_timeout for meeting task lookup", exc_info=True)

            try:
                for clause in lookup_clauses:
                    remaining = normalized_limit - len(tasks)
                    if remaining <= 0:
                        break
                    query_parts = [
                        "SELECT * FROM tasks WHERE",
                        clause,
                    ]
                    params = dict(base_params)
                    if workspace_id:
                        query_parts.append("AND workspace_id = :workspace_id")
                    query_parts.append("ORDER BY created_at ASC")
                    query_parts.append("LIMIT :limit")
                    params["limit"] = remaining

                    try:
                        rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
                    except Exception as exc:
                        logger.warning(
                            "Meeting task lookup clause skipped after query failure: session=%s clause=%s error=%s",
                            effective_session_id,
                            clause,
                            exc,
                        )
                        try:
                            conn.rollback()
                        except Exception:
                            logger.debug("Unable to rollback failed meeting task lookup", exc_info=True)
                        continue

                    for row in rows:
                        task = self._row_to_task(row)
                        if task.id in seen_ids:
                            continue
                        seen_ids.add(task.id)
                        tasks.append(task)
            finally:
                try:
                    conn.execute(text("RESET statement_timeout"))
                except Exception:
                    logger.debug("Unable to reset statement_timeout for meeting task lookup", exc_info=True)

        return tasks

    def list_running_playbook_execution_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 200
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.RUNNING.value,
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        query_parts.append("ORDER BY created_at ASC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_frontier_running_pending_tasks(
        self, workspace_id: Optional[str] = None, limit: int = 200
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            AND frontier_state = :frontier_state
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "running",
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        query_parts.append("ORDER BY started_at ASC NULLS LAST, created_at ASC, id ASC")
        query_parts.append("LIMIT :limit")
        params["limit"] = limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]
