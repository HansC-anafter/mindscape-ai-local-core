"""Control-plane pressure synthesis for host resource summary."""

from __future__ import annotations

from typing import Any, Mapping


CONTROL_PLANE_KINDS = {
    "postgresql",
    "pgbouncer",
    "local_core_backend",
    "web_console_frontend",
    "browser_or_playwright",
    "projection_maintenance",
}


def _memory_mb(consumer: Mapping[str, Any]) -> float:
    try:
        return float(consumer.get("memory_mb") or 0)
    except Exception:
        return 0.0


def build_control_plane_pressure(consumers: list[Any]) -> dict[str, Any]:
    control_consumers = [
        dict(consumer)
        for consumer in consumers
        if isinstance(consumer, Mapping) and consumer.get("kind") in CONTROL_PLANE_KINDS
    ]
    memory_mb = round(sum(_memory_mb(consumer) for consumer in control_consumers), 1)
    if memory_mb >= 4096:
        state = "critical"
    elif memory_mb >= 2048 or len(control_consumers) >= 8:
        state = "watch"
    else:
        state = "ok"
    blockers = sorted(control_consumers, key=_memory_mb, reverse=True)[:3]
    actions: list[str] = []
    if state != "ok":
        actions.append("defer_projection_maintenance")
        actions.append("avoid_dashboard_candidate_polling")
    return {
        "state": state,
        "memory_mb": memory_mb,
        "process_count": len(control_consumers),
        "primary_blockers": [
            {
                "consumer_id": consumer.get("consumer_id"),
                "label": consumer.get("label"),
                "memory_mb": consumer.get("memory_mb"),
                "kind": consumer.get("kind"),
            }
            for consumer in blockers
        ],
        "recommended_actions": actions,
    }
