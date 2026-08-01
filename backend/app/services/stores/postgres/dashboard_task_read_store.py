"""Query-shaped PostgreSQL reads for Dashboard task summaries."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase


_MAX_PAGE_SIZE = 200


def _normalized_ids(values: Iterable[str]) -> List[str]:
    return list(
        dict.fromkeys(
            normalized
            for value in values
            if (normalized := str(value or "").strip())
        )
    )


class DashboardTaskReadStore(PostgresStoreBase):
    """Keep Dashboard task reads exact, compact, and payload bounded."""

    def list_pending_items(
        self,
        workspace_ids: Iterable[str],
        *,
        limit: int,
        offset: int,
    ) -> List[Dict[str, Any]]:
        normalized_workspace_ids = _normalized_ids(workspace_ids)
        if not normalized_workspace_ids:
            return []

        normalized_limit = max(1, min(_MAX_PAGE_SIZE, int(limit or 50)))
        normalized_offset = max(0, int(offset or 0))
        candidate_limit = normalized_offset + normalized_limit
        params: Dict[str, Any] = {
            "candidate_limit": candidate_limit,
            "limit": normalized_limit,
            "offset": normalized_offset,
        }
        candidate_queries: List[str] = []
        for index, workspace_id in enumerate(normalized_workspace_ids):
            parameter_name = f"workspace_id_{index}"
            params[parameter_name] = workspace_id
            candidate_queries.append(
                f"""
                (
                    SELECT id AS task_id, workspace_id, created_at
                    FROM tasks
                    WHERE workspace_id = :{parameter_name}
                      AND status = 'pending'
                    ORDER BY created_at DESC, id DESC
                    LIMIT :candidate_limit
                )
                """
            )

        query = text(
            f"""
            WITH workspace_candidates AS MATERIALIZED (
                {" UNION ALL ".join(candidate_queries)}
            ),
            page_ids AS MATERIALIZED (
                SELECT task_id, workspace_id, created_at
                FROM workspace_candidates
                ORDER BY created_at DESC, task_id DESC
                LIMIT :limit OFFSET :offset
            )
            SELECT
                projection.task_id,
                projection.workspace_id,
                projection.execution_id,
                projection.pack_id,
                projection.task_type,
                source.status,
                COALESCE(
                    projection.summary,
                    source.params ->> 'description',
                    ''
                ) AS description,
                projection.created_at,
                projection.started_at,
                projection.updated_at
            FROM page_ids
            JOIN tasks AS source ON source.id = page_ids.task_id
            JOIN task_summary_projection AS projection
              ON projection.task_id = page_ids.task_id
            ORDER BY page_ids.created_at DESC, page_ids.task_id DESC
            """
        )
        with self.get_connection() as conn:
            self._set_statement_timeout(conn)
            rows = conn.execute(query, params).fetchall()
        return [dict(row._mapping) for row in rows]

    def count_pending_tasks(self, workspace_ids: Iterable[str]) -> int:
        normalized_workspace_ids = _normalized_ids(workspace_ids)
        if not normalized_workspace_ids:
            return 0
        query = text(
            """
            SELECT COUNT(*) AS count
            FROM tasks
            WHERE workspace_id = ANY(CAST(:workspace_ids AS text[]))
              AND status = 'pending'
            """
        )
        with self.get_connection() as conn:
            self._set_statement_timeout(conn)
            row = conn.execute(
                query,
                {"workspace_ids": normalized_workspace_ids},
            ).fetchone()
        return int(row.count if row is not None else 0)

    def count_tasks_by_execution_ids(
        self,
        workspace_id: str,
        execution_ids: Iterable[str],
    ) -> Dict[str, int]:
        normalized_execution_ids = _normalized_ids(execution_ids)
        if not normalized_execution_ids:
            return {}
        query = text(
            """
            SELECT execution_id, COUNT(*) AS count
            FROM tasks
            WHERE workspace_id = :workspace_id
              AND execution_id = ANY(CAST(:execution_ids AS text[]))
            GROUP BY execution_id
            """
        )
        with self.get_connection() as conn:
            self._set_statement_timeout(conn)
            rows = conn.execute(
                query,
                {
                    "workspace_id": workspace_id,
                    "execution_ids": normalized_execution_ids,
                },
            ).fetchall()
        return {str(row.execution_id): int(row.count) for row in rows}

    def _set_statement_timeout(self, conn) -> None:
        conn.execute(text("SET LOCAL statement_timeout = '10000ms'"))
