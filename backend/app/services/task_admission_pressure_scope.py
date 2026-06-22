"""Admission pressure scoping for producer-side backpressure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION,
    normalize_queue_partition,
)
from backend.app.services.runner_topology.task_family_registry import (
    MANAGED_BROWSER_BATCH_TASK_FAMILY,
    RESOURCE_CLASS_BROWSER,
    resolve_browser_fairness_lane_key,
    resolve_managed_batch_binding,
)


@dataclass(frozen=True)
class AdmissionPressureScope:
    """SQL filter describing which work contributes to admission pressure."""

    scope_name: str = "queue_shard"
    sql_clause: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)


DEFAULT_ADMISSION_PRESSURE_SCOPE = AdmissionPressureScope()


def _clean_token(value: Any) -> Optional[str]:
    if isinstance(value, str):
        token = value.strip()
        return token or None
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    token = str(value).strip()
    return token or None


def _context_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _context_token(context: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        token = _clean_token(context.get(key))
        if token:
            return token
    return None


def _context_declares_managed_browser_batch(context: Mapping[str, Any]) -> bool:
    task_family = _context_token(context, "task_family")
    if task_family != MANAGED_BROWSER_BATCH_TASK_FAMILY:
        return False
    resource_class = (_context_token(context, "resource_class") or "").lower()
    return resource_class in {"", RESOURCE_CLASS_BROWSER}


def _resolve_task_fairness_lane(task: Any, context: Mapping[str, Any]) -> Optional[str]:
    lane = _context_token(context, "fairness_lane_key")
    if lane and _context_declares_managed_browser_batch(context):
        return lane

    pack_id = _clean_token(getattr(task, "pack_id", None))
    playbook_code = _context_token(context, "playbook_code", "pack_id") or pack_id

    binding = resolve_managed_batch_binding(pack_id or playbook_code, context)
    if binding is not None:
        return lane or binding.fairness_lane_key

    if not _context_declares_managed_browser_batch(context):
        return None

    return lane or resolve_browser_fairness_lane_key(pack_id or playbook_code, playbook_code)


def resolve_admission_pressure_scope(
    task: Any,
    *,
    queue_shard: Any,
) -> AdmissionPressureScope:
    """Return the pressure scope for admission decisions on a queue shard."""

    normalized_queue = normalize_queue_partition(queue_shard, fallback=None)
    if normalized_queue != DEFAULT_LOCAL_BROWSER_QUEUE_PARTITION:
        return DEFAULT_ADMISSION_PRESSURE_SCOPE

    context = _context_mapping(getattr(task, "execution_context", None))
    lane = _resolve_task_fairness_lane(task, context)
    if not lane:
        return DEFAULT_ADMISSION_PRESSURE_SCOPE

    return AdmissionPressureScope(
        scope_name=f"browser_fairness_lane:{lane}",
        sql_clause=(
            "AND COALESCE("
            "NULLIF(execution_context->>'fairness_lane_key', ''), "
            "NULLIF(execution_context->>'playbook_code', ''), "
            "pack_id"
            ") = :admission_pressure_lane_key"
        ),
        params={"admission_pressure_lane_key": lane},
    )
