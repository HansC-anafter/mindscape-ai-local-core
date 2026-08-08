"""Query-shaped PostgreSQL reads for the complete Dashboard read plane."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy import text

from app.models.workspace import TaskStatus

from ..postgres_base import PostgresStoreBase
from .dashboard_read_queries import (
    ASSIGNMENT_BOUNDED_TOTAL_QUERY,
    ASSIGNMENT_PAGE_QUERY,
    CASE_BOUNDED_TOTAL_QUERY,
    CASE_PAGE_QUERY,
    INBOX_PAGE_QUERY,
    PENDING_TASK_COUNT_QUERY,
    SUMMARY_COUNTS_QUERY,
    WORKSPACE_BOUNDED_TOTAL_QUERY,
    WORKSPACE_PAGE_QUERY,
)


_MAX_PAGE_SIZE = 200
_TASK_SOURCE_STATUSES = tuple(status.value for status in TaskStatus) + ("cancelled",)


def _normalized_ids(values: Iterable[str]) -> List[str]:
    return list(
        dict.fromkeys(
            normalized
            for value in values
            if (normalized := str(value or "").strip())
        )
    )


def _normalized_page(limit: int, offset: int) -> Tuple[int, int]:
    return (
        max(1, min(_MAX_PAGE_SIZE, int(limit or 50))),
        max(0, int(offset or 0)),
    )


class DashboardReadStore(PostgresStoreBase):
    """Keep every Dashboard read compact, bounded, and statement-timed."""

    def get_summary_counts(self, workspace_ids: Iterable[str]) -> Dict[str, int]:
        normalized_workspace_ids = _normalized_ids(workspace_ids)
        if not normalized_workspace_ids:
            return self._empty_summary_counts()

        with self.get_connection() as conn:
            self._set_statement_timeout(conn)
            row = conn.execute(
                SUMMARY_COUNTS_QUERY,
                {"workspace_ids": normalized_workspace_ids},
            ).fetchone()
        if row is None:
            return self._empty_summary_counts()
        return {
            "open_assignments": int(row.open_assignments or 0),
            "open_cases": int(row.open_cases or 0),
            "blocked_cases": int(row.blocked_cases or 0),
            "running_jobs": int(row.running_jobs or 0),
        }

    def list_inbox_page(
        self,
        workspace_ids: Iterable[str],
        *,
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        normalized_workspace_ids = _normalized_ids(workspace_ids)
        if not normalized_workspace_ids:
            return [], 0
        normalized_limit, normalized_offset = _normalized_page(limit, offset)
        params = {
            "workspace_ids": normalized_workspace_ids,
            "candidate_limit": normalized_offset + normalized_limit,
            "limit": normalized_limit,
            "offset": normalized_offset,
        }
        with self.get_connection() as conn:
            self._set_statement_timeout(conn)
            rows = conn.execute(INBOX_PAGE_QUERY, params).fetchall()
            total_row = conn.execute(
                PENDING_TASK_COUNT_QUERY,
                {"workspace_ids": normalized_workspace_ids},
            ).fetchone()
        return self._rows_without_total(rows), int(total_row.count if total_row else 0)

    def list_case_page(
        self,
        workspace_ids: Iterable[str],
        *,
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self._list_bounded_page(
            workspace_ids,
            limit=limit,
            offset=offset,
            page_query=CASE_PAGE_QUERY,
            total_query=CASE_BOUNDED_TOTAL_QUERY,
        )

    def list_assignment_page(
        self,
        workspace_ids: Iterable[str],
        *,
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self._list_bounded_page(
            workspace_ids,
            limit=limit,
            offset=offset,
            page_query=ASSIGNMENT_PAGE_QUERY,
            total_query=ASSIGNMENT_BOUNDED_TOTAL_QUERY,
            extra_params={"source_statuses": list(_TASK_SOURCE_STATUSES)},
        )

    def list_workspace_page(
        self,
        workspace_ids: Iterable[str],
        *,
        search: str | None,
        limit: int,
        offset: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self._list_bounded_page(
            workspace_ids,
            limit=limit,
            offset=offset,
            page_query=WORKSPACE_PAGE_QUERY,
            total_query=WORKSPACE_BOUNDED_TOTAL_QUERY,
            extra_params={"search": search if search else None},
        )

    def _list_bounded_page(
        self,
        workspace_ids: Iterable[str],
        *,
        limit: int,
        offset: int,
        page_query,
        total_query,
        extra_params: Dict[str, Any] | None = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        normalized_workspace_ids = _normalized_ids(workspace_ids)
        if not normalized_workspace_ids:
            return [], 0
        normalized_limit, normalized_offset = _normalized_page(limit, offset)
        params: Dict[str, Any] = {
            "workspace_ids": normalized_workspace_ids,
            "limit": normalized_limit,
            "offset": normalized_offset,
        }
        params.update(extra_params or {})

        with self.get_connection() as conn:
            self._set_statement_timeout(conn)
            rows = conn.execute(page_query, params).fetchall()
            if rows:
                total = int(rows[0].bounded_total or 0)
            elif normalized_offset == 0:
                total = 0
            else:
                total_row = conn.execute(total_query, params).fetchone()
                total = int(total_row.count if total_row else 0)
        return self._rows_without_total(rows), total

    @staticmethod
    def _rows_without_total(rows) -> List[Dict[str, Any]]:
        return [
            {
                key: value
                for key, value in row._mapping.items()
                if key != "bounded_total"
            }
            for row in rows
        ]

    @staticmethod
    def _empty_summary_counts() -> Dict[str, int]:
        return {
            "open_assignments": 0,
            "open_cases": 0,
            "blocked_cases": 0,
            "running_jobs": 0,
        }

    @staticmethod
    def _set_statement_timeout(conn) -> None:
        conn.execute(text("SET LOCAL statement_timeout = '10000ms'"))
