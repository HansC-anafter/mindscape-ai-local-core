"""Bounded PostgreSQL projections for Dashboard workload reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase


@dataclass(frozen=True)
class DashboardWorkloadCounts:
    """Exact counts backed by product-level execution entities."""

    open_cases: int
    blocked_cases: int
    running_jobs: int


class PostgresDashboardWorkloadStore(PostgresStoreBase):
    """Purpose-built read store for Dashboard workload projections."""

    def load_counts(
        self,
        workspace_ids: Sequence[str],
    ) -> DashboardWorkloadCounts:
        scope = self._workspace_scope(workspace_ids)
        if not scope:
            return DashboardWorkloadCounts(0, 0, 0)

        query = text(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'running'
                ) AS open_cases,
                COUNT(*) FILTER (
                    WHERE status IN ('paused', 'failed')
                ) AS blocked_cases
            FROM playbook_executions
            WHERE workspace_id = ANY(CAST(:workspace_ids AS VARCHAR[]))
              AND status IN ('running', 'paused', 'failed')
            """
        )
        with self.get_connection() as connection:
            row = connection.execute(
                query,
                {"workspace_ids": list(scope)},
            ).fetchone()

        if row is None:
            return DashboardWorkloadCounts(0, 0, 0)
        open_cases = int(row.open_cases or 0)
        return DashboardWorkloadCounts(
            open_cases=open_cases,
            blocked_cases=int(row.blocked_cases or 0),
            running_jobs=open_cases,
        )

    @staticmethod
    def _workspace_scope(workspace_ids: Sequence[str]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    str(workspace_id).strip()
                    for workspace_id in workspace_ids
                    if str(workspace_id).strip()
                }
            )
        )
