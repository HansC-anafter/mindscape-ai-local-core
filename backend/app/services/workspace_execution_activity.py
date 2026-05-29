"""Core read model for workspace execution activity."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import bindparam, text

from app.services.stores.postgres_base import PostgresStoreBase


ACTIVE_EXECUTION_STATUSES = ("running", "queued", "pending", "paused")
FAILED_EXECUTION_STATUSES = ("failed", "cancelled", "cancelled_by_user", "expired")
COMPLETED_EXECUTION_STATUSES = ("succeeded", "completed")
PENDING_EXECUTION_STATUSES = ("pending", "queued", "paused")


def _normalize_limit(value: int, *, default: int, maximum: int) -> int:
    return max(1, min(maximum, int(value or default)))


def _normalize_offset(value: int) -> int:
    return max(0, int(value or 0))


def _normalize_values(values: Optional[Sequence[str] | str]) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        source: Sequence[str] = [values]
    else:
        source = values
    normalized = [str(item).strip() for item in source if str(item).strip()]
    return list(dict.fromkeys(normalized))


def _normalize_statuses(values: Optional[Sequence[str] | str]) -> List[str]:
    return [item.lower() for item in _normalize_values(values)]


class WorkspaceExecutionActivityStore(PostgresStoreBase):
    """Read bounded workspace execution activity from task projections."""

    def list_executions(
        self,
        workspace_id: str,
        *,
        limit: int = 30,
        offset: int = 0,
        statuses: Optional[Sequence[str] | str] = None,
        playbook_code: Optional[Sequence[str] | str] = None,
        playbook_code_prefix: Optional[str] = None,
        parent_execution_id: Optional[str] = None,
        exclude_playbook_code: Optional[Sequence[str] | str] = None,
        active_only: bool = False,
        order_by: str = "created_at",
        order: str = "desc",
    ) -> Dict[str, Any]:
        normalized_limit = _normalize_limit(limit, default=30, maximum=200)
        normalized_offset = _normalize_offset(offset)
        query_parts = self._execution_filter_sql(
            workspace_id=workspace_id,
            statuses=(
                ACTIVE_EXECUTION_STATUSES
                if active_only and not _normalize_statuses(statuses)
                else statuses
            ),
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=parent_execution_id,
            exclude_playbook_code=exclude_playbook_code,
            exclude_admission_deferred=active_only,
        )
        params = {
            **query_parts["params"],
            "limit": normalized_limit + 1,
            "offset": normalized_offset,
        }
        statement = text(
            f"""
            SELECT {self._select_columns()}
            FROM task_summary_projection
            WHERE {" AND ".join(query_parts["clauses"])}
            {self._order_clause(order_by=order_by, order=order)}
            LIMIT :limit OFFSET :offset
            """
        )
        statement = self._bind_expanding(statement, query_parts)
        with self.get_connection() as conn:
            rows = conn.execute(statement, params).fetchall()

        has_more = len(rows) > normalized_limit
        execution_rows = rows[:normalized_limit]
        executions = [self._row_to_execution_payload(row) for row in execution_rows]
        return {
            "executions": executions,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "returned": len(executions),
            "has_more": has_more,
            "next_offset": (
                normalized_offset + len(executions)
                if has_more
                else None
            ),
        }

    def list_execution_groups(
        self,
        workspace_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        statuses: Optional[Sequence[str] | str] = None,
        playbook_code: Optional[Sequence[str] | str] = None,
        playbook_code_prefix: Optional[str] = None,
        exclude_playbook_code: Optional[Sequence[str] | str] = None,
    ) -> Dict[str, Any]:
        normalized_limit = _normalize_limit(limit, default=20, maximum=100)
        normalized_offset = _normalize_offset(offset)
        scan_limit = min(max((normalized_offset + normalized_limit + 1) * 25, 200), 2000)
        query_parts = self._execution_filter_sql(
            workspace_id=workspace_id,
            statuses=statuses,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=None,
            exclude_playbook_code=exclude_playbook_code,
            exclude_admission_deferred=False,
        )
        group_clauses = [*query_parts["clauses"], "parent_execution_id IS NOT NULL"]
        params = {
            **query_parts["params"],
            "limit": normalized_limit + 1,
            "offset": normalized_offset,
            "scan_limit": scan_limit,
        }
        statement = text(
            f"""
            WITH bounded AS (
                SELECT
                    {self._select_columns()},
                    COALESCE(started_at, created_at) AS sort_at
                FROM task_summary_projection
                WHERE {" AND ".join(group_clauses)}
                ORDER BY created_at DESC NULLS LAST, task_id DESC
                LIMIT :scan_limit
            ),
            grouped AS (
                SELECT
                    parent_execution_id,
                    COUNT(*) AS total,
                    SUM(
                        CASE WHEN LOWER(status) IN ('succeeded', 'completed')
                        THEN 1 ELSE 0 END
                    ) AS completed,
                    SUM(
                        CASE WHEN LOWER(status) IN (
                            'failed',
                            'cancelled',
                            'cancelled_by_user',
                            'expired'
                        )
                        THEN 1 ELSE 0 END
                    ) AS failed,
                    SUM(CASE WHEN LOWER(status) = 'running' THEN 1 ELSE 0 END) AS running,
                    SUM(
                        CASE WHEN LOWER(status) IN ('pending', 'queued', 'paused')
                        THEN 1 ELSE 0 END
                    ) AS pending,
                    MAX(sort_at) AS latest_at
                FROM bounded
                GROUP BY parent_execution_id
            ),
            paged AS (
                SELECT *
                FROM grouped
                ORDER BY latest_at DESC NULLS LAST, parent_execution_id DESC
                LIMIT :limit OFFSET :offset
            ),
            representative AS (
                SELECT *
                FROM (
                    SELECT
                        bounded.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY parent_execution_id
                            ORDER BY sort_at DESC NULLS LAST, created_at DESC NULLS LAST, task_id DESC
                        ) AS rn
                    FROM bounded
                ) ranked
                WHERE rn = 1
            )
            SELECT
                paged.parent_execution_id AS group_parent_execution_id,
                paged.total,
                paged.completed,
                paged.failed,
                paged.running,
                paged.pending,
                paged.latest_at,
                representative.*
            FROM paged
            JOIN representative
              ON representative.parent_execution_id = paged.parent_execution_id
            ORDER BY paged.latest_at DESC NULLS LAST, paged.parent_execution_id DESC
            """
        )
        statement = self._bind_expanding(statement, query_parts)
        with self.get_connection() as conn:
            rows = conn.execute(statement, params).fetchall()

        has_more = len(rows) > normalized_limit
        groups = []
        for row in rows[:normalized_limit]:
            mapping = self._mapping(row)
            groups.append(
                {
                    "parent_execution_id": mapping.get("group_parent_execution_id"),
                    "summary": {
                        "total": int(mapping.get("total") or 0),
                        "completed": int(mapping.get("completed") or 0),
                        "failed": int(mapping.get("failed") or 0),
                        "running": int(mapping.get("running") or 0),
                        "pending": int(mapping.get("pending") or 0),
                    },
                    "latest_at": mapping.get("latest_at"),
                    "representative": self._row_to_execution_payload(row),
                }
            )

        ungrouped = self._list_ungrouped_executions(
            workspace_id=workspace_id,
            statuses=statuses,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            exclude_playbook_code=exclude_playbook_code,
            limit=10,
        )
        return {
            "groups": groups,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "returned_groups": len(groups),
            "has_more_groups": has_more,
            "next_offset": (
                normalized_offset + len(groups)
                if has_more
                else None
            ),
            "ungrouped": ungrouped,
        }

    def list_execution_group_children(
        self,
        workspace_id: str,
        *,
        parent_execution_id: str,
        limit: int = 20,
        offset: int = 0,
        statuses: Optional[Sequence[str] | str] = None,
        playbook_code: Optional[Sequence[str] | str] = None,
        playbook_code_prefix: Optional[str] = None,
        exclude_playbook_code: Optional[Sequence[str] | str] = None,
    ) -> Dict[str, Any]:
        normalized_limit = _normalize_limit(limit, default=20, maximum=100)
        normalized_offset = _normalize_offset(offset)
        query_parts = self._execution_filter_sql(
            workspace_id=workspace_id,
            statuses=statuses,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=parent_execution_id,
            exclude_playbook_code=exclude_playbook_code,
            exclude_admission_deferred=False,
        )
        params = {
            **query_parts["params"],
            "limit": normalized_limit + 1,
            "offset": normalized_offset,
        }
        children_statement = text(
            f"""
            SELECT {self._select_columns()}
            FROM task_summary_projection
            WHERE {" AND ".join(query_parts["clauses"])}
            ORDER BY COALESCE(started_at, created_at) DESC NULLS LAST, task_id DESC
            LIMIT :limit OFFSET :offset
            """
        )
        count_statement = text(
            f"""
            SELECT COUNT(*) AS total
            FROM task_summary_projection
            WHERE {" AND ".join(query_parts["clauses"])}
            """
        )
        children_statement = self._bind_expanding(children_statement, query_parts)
        count_statement = self._bind_expanding(count_statement, query_parts)
        with self.get_connection() as conn:
            total_row = conn.execute(count_statement, query_parts["params"]).fetchone()
            rows = conn.execute(children_statement, params).fetchall()

        total = int(self._mapping(total_row).get("total") or 0) if total_row else 0
        has_more = len(rows) > normalized_limit
        executions = [
            self._row_to_execution_payload(row)
            for row in rows[:normalized_limit]
        ]
        return {
            "parent_execution_id": parent_execution_id,
            "executions": executions,
            "total": total,
            "offset": normalized_offset,
            "limit": normalized_limit,
            "returned": len(executions),
            "has_more": has_more or normalized_offset + len(executions) < total,
            "next_offset": (
                normalized_offset + len(executions)
                if has_more or normalized_offset + len(executions) < total
                else None
            ),
        }

    def _list_ungrouped_executions(
        self,
        *,
        workspace_id: str,
        statuses: Optional[Sequence[str] | str],
        playbook_code: Optional[Sequence[str] | str],
        playbook_code_prefix: Optional[str],
        exclude_playbook_code: Optional[Sequence[str] | str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        query_parts = self._execution_filter_sql(
            workspace_id=workspace_id,
            statuses=statuses,
            playbook_code=playbook_code,
            playbook_code_prefix=playbook_code_prefix,
            parent_execution_id=None,
            exclude_playbook_code=exclude_playbook_code,
            exclude_admission_deferred=False,
        )
        clauses = [*query_parts["clauses"], "parent_execution_id IS NULL"]
        params = {**query_parts["params"], "limit": _normalize_limit(limit, default=10, maximum=50)}
        statement = text(
            f"""
            SELECT {self._select_columns()}
            FROM task_summary_projection
            WHERE {" AND ".join(clauses)}
            ORDER BY created_at DESC NULLS LAST, task_id DESC
            LIMIT :limit
            """
        )
        statement = self._bind_expanding(statement, query_parts)
        with self.get_connection() as conn:
            rows = conn.execute(statement, params).fetchall()
        return [self._row_to_execution_payload(row) for row in rows]

    def _execution_filter_sql(
        self,
        *,
        workspace_id: str,
        statuses: Optional[Sequence[str] | str],
        playbook_code: Optional[Sequence[str] | str],
        playbook_code_prefix: Optional[str],
        parent_execution_id: Optional[str],
        exclude_playbook_code: Optional[Sequence[str] | str],
        exclude_admission_deferred: bool,
    ) -> Dict[str, Any]:
        clauses = ["workspace_id = :workspace_id", "execution_id IS NOT NULL"]
        params: Dict[str, Any] = {"workspace_id": workspace_id}
        expanding: List[str] = []

        normalized_statuses = _normalize_statuses(statuses)
        if normalized_statuses:
            clauses.append("status IN :statuses")
            params["statuses"] = normalized_statuses
            expanding.append("statuses")

        playbook_codes = _normalize_values(playbook_code)
        if playbook_codes:
            clauses.append("pack_id IN :playbook_codes")
            params["playbook_codes"] = playbook_codes
            expanding.append("playbook_codes")
        elif playbook_code_prefix:
            clauses.append("pack_id LIKE :playbook_code_prefix")
            params["playbook_code_prefix"] = f"{playbook_code_prefix}%"

        if parent_execution_id:
            clauses.append("parent_execution_id = :parent_execution_id")
            params["parent_execution_id"] = parent_execution_id

        excluded_playbook_codes = _normalize_values(exclude_playbook_code)
        if excluded_playbook_codes:
            clauses.append("(pack_id IS NULL OR pack_id NOT IN :excluded_playbook_codes)")
            params["excluded_playbook_codes"] = excluded_playbook_codes
            expanding.append("excluded_playbook_codes")

        if exclude_admission_deferred:
            clauses.append("COALESCE(blocked_reason, '') <> 'admission_deferred'")
            clauses.append(
                "(frontier_state IS NULL OR frontier_state IN ('ready', 'running'))"
            )

        return {"clauses": clauses, "params": params, "expanding": expanding}

    def _bind_expanding(self, statement, query_parts: Dict[str, Any]):
        for name in query_parts.get("expanding", []):
            statement = statement.bindparams(bindparam(name, expanding=True))
        return statement

    def _order_clause(self, *, order_by: str, order: str) -> str:
        safe_order = "DESC" if str(order).lower() == "desc" else "ASC"
        safe_key = str(order_by or "created_at").strip().lower()
        if safe_key == "status":
            return (
                "ORDER BY CASE LOWER(status) "
                "WHEN 'running' THEN 0 "
                "WHEN 'queued' THEN 1 "
                "WHEN 'paused' THEN 2 "
                "WHEN 'pending' THEN 3 "
                "WHEN 'failed' THEN 4 "
                "WHEN 'cancelled' THEN 5 "
                "WHEN 'cancelled_by_user' THEN 6 "
                "WHEN 'expired' THEN 7 "
                "ELSE 8 END, "
                f"status {safe_order}, updated_at DESC NULLS LAST, task_id DESC"
            )
        if safe_key == "updated_at":
            return f"ORDER BY updated_at {safe_order} NULLS LAST, task_id DESC"
        if safe_key == "started_at":
            return f"ORDER BY started_at {safe_order} NULLS LAST, task_id DESC"
        if safe_key == "completed_at":
            return f"ORDER BY completed_at {safe_order} NULLS LAST, task_id DESC"
        return f"ORDER BY created_at {safe_order} NULLS LAST, task_id DESC"

    def _select_columns(self) -> str:
        return """
            task_id,
            workspace_id,
            execution_id,
            parent_execution_id,
            project_id,
            pack_id,
            task_type,
            status,
            queue_shard,
            dedupe_key,
            summary,
            error_summary,
            compact_inputs,
            created_at,
            next_eligible_at,
            blocked_reason,
            frontier_state,
            frontier_enqueued_at,
            started_at,
            completed_at,
            updated_at,
            last_event_at
        """

    def _row_to_execution_payload(self, row: Any) -> Dict[str, Any]:
        mapping = self._mapping(row)
        status = str(mapping.get("status") or "")
        compact_inputs = self._as_dict(mapping.get("compact_inputs"))
        context = self._compact_execution_context(mapping, compact_inputs)
        return {
            "id": mapping.get("task_id"),
            "task_id": mapping.get("task_id"),
            "workspace_id": mapping.get("workspace_id"),
            "message_id": mapping.get("task_id"),
            "execution_id": mapping.get("execution_id"),
            "parent_execution_id": mapping.get("parent_execution_id"),
            "project_id": mapping.get("project_id"),
            "pack_id": mapping.get("pack_id") or "",
            "task_type": mapping.get("task_type"),
            "status": status,
            "params": compact_inputs,
            "result": None,
            "execution_context": context,
            "meeting_session_id": None,
            "storyline_tags": [],
            "created_at": self._datetime_or_now(mapping.get("created_at")),
            "next_eligible_at": self._datetime_or_now(mapping.get("next_eligible_at")),
            "blocked_reason": mapping.get("blocked_reason"),
            "blocked_payload": None,
            "queue_shard": mapping.get("queue_shard") or "default",
            "concurrency_key": mapping.get("dedupe_key"),
            "frontier_state": mapping.get("frontier_state") or self._frontier_state(status),
            "frontier_enqueued_at": mapping.get("frontier_enqueued_at"),
            "runner_id": None,
            "heartbeat_at": None,
            "started_at": mapping.get("started_at"),
            "completed_at": mapping.get("completed_at"),
            "error": mapping.get("error_summary"),
            "summary": mapping.get("summary"),
            "updated_at": mapping.get("updated_at"),
            "last_event_at": mapping.get("last_event_at"),
        }

    def _compact_execution_context(
        self,
        mapping: Dict[str, Any],
        compact_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = {
            "project_id": mapping.get("project_id"),
            "status": mapping.get("status"),
            "summary": mapping.get("summary"),
        }
        if compact_inputs:
            context["inputs"] = compact_inputs
            for key in ("target_username", "target_handle", "reference_id", "source_handle"):
                if compact_inputs.get(key):
                    context[key] = compact_inputs.get(key)
        return {key: value for key, value in context.items() if value not in (None, "", [], {})}

    def _mapping(self, row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        if isinstance(row, dict):
            return row
        return dict(row)

    def _as_dict(self, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _datetime_or_now(self, value: Optional[datetime]) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.now(timezone.utc)

    def _frontier_state(self, status: str) -> str:
        if status == "running":
            return "running"
        if status in {*COMPLETED_EXECUTION_STATUSES, *FAILED_EXECUTION_STATUSES}:
            return "done"
        return "ready"
