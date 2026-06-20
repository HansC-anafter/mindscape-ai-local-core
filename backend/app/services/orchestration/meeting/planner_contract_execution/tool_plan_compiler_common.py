"""Shared primitives for planner tool plan compilation."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional

from backend.app.services.orchestration.meeting.planner_contract_execution.tool_plan_models import (
    PlannerToolPlanStep,
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_step(
    *,
    tool: Dict[str, Any],
    role: str,
    category_id: str,
    category_label: str,
    arguments: Dict[str, Any],
    depends_on: Optional[List[str]] = None,
    role_step_ids: Optional[Dict[str, str]] = None,
    meeting_role_profile_code: Optional[str] = None,
    meeting_lane_code: Optional[str] = None,
    pack_role_name: Optional[str] = None,
    resource_budget_class: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> PlannerToolPlanStep:
    contract = dict(tool.get("planner_contract") or {})
    hints = execution_hints(tool)
    step_id = f"{role}_{category_id}"
    return PlannerToolPlanStep(
        step_id=step_id,
        role=role,
        category_id=category_id,
        category_label=category_label,
        tool_name=str(tool.get("canonical_tool_name") or ""),
        resource_kind=str(contract.get("resource_kind") or ""),
        effect=str(contract.get("effect") or ""),
        arguments=arguments,
        input_bindings=scoped_input_bindings(
            hints.get("input_bindings"),
            role_step_ids or {},
        ),
        result_selectors={
            str(key): str(value)
            for key, value in dict(hints.get("result_selectors") or {}).items()
            if str(key or "").strip() and str(value or "").strip()
        },
        max_selector_fanout=bounded_limit(tool, default=200),
        depends_on=depends_on or [],
        planner_contract=contract,
        meeting_role_profile_code=meeting_role_profile_code,
        meeting_lane_code=meeting_lane_code,
        pack_role_name=pack_role_name,
        resource_budget_class=resource_budget_class,
        trace_id=trace_id,
    )


def flag_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def pack_enabled_for_role_profiles(pack_id: str) -> bool:
    raw_codes = str(os.getenv("MEETING_ROLE_PROFILES_ENABLED_PACK_CODES", "")).strip()
    if not raw_codes:
        return True
    return pack_id in {code.strip() for code in raw_codes.split(",") if code.strip()}


def has_polling_hint(payload: Dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "polling",
            "polling_interval",
            "polling_interval_ms",
            "poll_interval",
            "poll_interval_ms",
        )
    )


def is_world_memory_write(*, resource_kind: str, effect: str) -> bool:
    if effect == "read":
        return False
    value = resource_kind.strip().lower()
    return value.startswith("world_memory") or value in {
        "world_card_projection",
        "world_memory_packet",
        "canonical_memory_item",
    }


def optional_string(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return [str(item).strip() for item in values if str(item or "").strip()]


def find_tool(
    planner_tools: Iterable[Dict[str, Any]],
    *,
    resource_kind: str,
    effect: str,
) -> Optional[Dict[str, Any]]:
    for tool in planner_tools:
        contract = dict(tool.get("planner_contract") or {})
        if (
            str(contract.get("resource_kind") or "").strip() == resource_kind
            and str(contract.get("effect") or "").strip().lower() == effect
        ):
            return dict(tool)
    return None


def bounded_limit(tool: Dict[str, Any], *, default: int) -> int:
    hints = execution_hints(tool)
    raw_value = hints.get("max_selector_fanout", default)
    try:
        return max(1, min(int(raw_value), 500))
    except (TypeError, ValueError):
        return default


def execution_hints(tool: Dict[str, Any]) -> Dict[str, Any]:
    hints = tool.get("execution_hints")
    if isinstance(hints, dict):
        return dict(hints)
    contract = tool.get("planner_contract")
    if isinstance(contract, dict) and isinstance(contract.get("execution_hints"), dict):
        return dict(contract.get("execution_hints") or {})
    return {}


def scoped_input_bindings(
    raw_bindings: Any,
    role_step_ids: Dict[str, str],
) -> Dict[str, Any]:
    if not isinstance(raw_bindings, dict):
        return {}

    def scope_expression(value: Any) -> Any:
        if isinstance(value, list):
            return [scope_expression(item) for item in value]
        if not isinstance(value, str):
            return value
        scoped = value
        for role, step_id in role_step_ids.items():
            scoped = scoped.replace(f"$steps.{role}.", f"$steps.{step_id}.")
        return scoped

    return {str(key): scope_expression(value) for key, value in raw_bindings.items()}
