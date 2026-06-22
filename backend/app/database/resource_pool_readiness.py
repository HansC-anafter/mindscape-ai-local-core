"""Pure resource-pool readiness summary for HA probe output."""

from __future__ import annotations

from typing import Any, Mapping


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _pgbouncer_waiting_total(pgbouncer: Mapping[str, Any]) -> int:
    return sum(
        _coerce_int(pgbouncer.get(key))
        for key in (
            "core_waiting",
            "vector_waiting",
            "readonly_core_waiting",
            "readonly_vector_waiting",
        )
    )


def build_resource_pool_readiness_summary(
    *,
    primary: Mapping[str, Any],
    pgbouncer: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify DB/PgBouncer pool pressure without issuing new probes."""

    waiting_total = _pgbouncer_waiting_total(pgbouncer)
    idle_in_transaction = _coerce_int(
        primary.get("app_idle_in_transaction_count"),
    )
    reasons: list[str] = []
    status = "open"

    if pgbouncer.get("enabled") and not pgbouncer.get("available"):
        status = "watch"
        reasons.append(str(pgbouncer.get("reason") or "pgbouncer_unavailable"))
    if waiting_total > 0:
        status = "paused"
        reasons.append("pgbouncer_client_waiting")
    if idle_in_transaction > 0:
        if status == "open":
            status = "watch"
        reasons.append("app_idle_in_transaction")
    if not primary.get("available"):
        status = "watch" if status == "open" else status
        reasons.append("primary_probe_unavailable")

    return {
        "status": status,
        "reasons": reasons,
        "pgbouncer_waiting_total": waiting_total,
        "app_idle_in_transaction_count": idle_in_transaction,
        "pgbouncer_available": bool(pgbouncer.get("available")),
        "primary_available": bool(primary.get("available")),
        "recommendation": _recommendation_for_status(status),
    }


def _recommendation_for_status(status: str) -> str:
    if status == "paused":
        return "hold new worker claims until PgBouncer waiting clients clear"
    if status == "watch":
        return "avoid widening pools; inspect probe reasons before dispatch expansion"
    return "keep current bounded worker and polling budgets"
