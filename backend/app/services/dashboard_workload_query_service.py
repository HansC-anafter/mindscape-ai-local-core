"""Facade for bounded Dashboard workload reads."""

from __future__ import annotations

import asyncio
from typing import Sequence

from ..models.dashboard import DashboardCountsDTO
from .stores.postgres.dashboard_workload_store import (
    PostgresDashboardWorkloadStore,
)


class DashboardWorkloadQueryService:
    """One facade seam for product-level Dashboard workload counts."""

    def __init__(
        self,
        store: PostgresDashboardWorkloadStore | None = None,
    ) -> None:
        self._store = store or PostgresDashboardWorkloadStore()

    async def load_counts(
        self,
        workspace_ids: Sequence[str],
    ) -> DashboardCountsDTO:
        counts = await asyncio.to_thread(
            self._store.load_counts,
            workspace_ids,
        )
        return DashboardCountsDTO(
            pending_decisions=0,
            open_assignments=0,
            open_cases=counts.open_cases,
            blocked_cases=counts.blocked_cases,
            running_jobs=counts.running_jobs,
            overdue_items=0,
            mentions=0,
            delegated_pending=0,
        )
