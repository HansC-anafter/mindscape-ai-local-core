"""Worker database budget decisions derived from PgBouncer pressure."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from backend.app.runner.db_pool_pressure import (
    DbPoolPressureDecision,
    pressure_wait_seconds,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
        return value if value > 0 else default
    except Exception:
        return default


def high_client_active_threshold() -> int:
    return _env_int("LOCAL_CORE_DB_BUDGET_HIGH_CLIENT_ACTIVE_THRESHOLD", 32)


def high_client_scan_multiplier() -> float:
    return min(
        1.0,
        max(
            0.1,
            _env_float("LOCAL_CORE_DB_BUDGET_HIGH_CLIENT_SCAN_MULTIPLIER", 0.5),
        ),
    )


@dataclass(frozen=True)
class WorkerDbBudgetDecision:
    allow_claim_scan: bool
    claim_scan_limit_multiplier: float
    allow_release_maintenance: bool
    allow_postgres_heartbeat: bool
    wait_seconds: int
    reason: str

    def apply_claim_scan_limit(self, configured_limit: int) -> int:
        if not self.allow_claim_scan:
            return 0
        return max(1, math.floor(configured_limit * self.claim_scan_limit_multiplier))


def _watched_client_active_total(decision: DbPoolPressureDecision) -> int:
    total = 0
    for pool in decision.pools:
        try:
            total += int(pool.get("cl_active") or 0)
        except Exception:
            continue
    return total


def decide_worker_db_budget(
    decision: DbPoolPressureDecision,
    *,
    profile_code: str,
    inflight: int,
    max_inflight: int,
) -> WorkerDbBudgetDecision:
    """Map shared PgBouncer pressure into bounded worker DB actions."""

    if decision.paused:
        return WorkerDbBudgetDecision(
            allow_claim_scan=False,
            claim_scan_limit_multiplier=0.0,
            allow_release_maintenance=False,
            allow_postgres_heartbeat=True,
            wait_seconds=max(1, decision.wait_seconds or pressure_wait_seconds()),
            reason=decision.reason,
        )

    active_total = _watched_client_active_total(decision)
    if active_total >= high_client_active_threshold():
        return WorkerDbBudgetDecision(
            allow_claim_scan=True,
            claim_scan_limit_multiplier=high_client_scan_multiplier(),
            allow_release_maintenance=False,
            allow_postgres_heartbeat=True,
            wait_seconds=0,
            reason="pgbouncer_client_active_budget",
        )

    return WorkerDbBudgetDecision(
        allow_claim_scan=True,
        claim_scan_limit_multiplier=1.0,
        allow_release_maintenance=True,
        allow_postgres_heartbeat=True,
        wait_seconds=0,
        reason=decision.reason,
    )
