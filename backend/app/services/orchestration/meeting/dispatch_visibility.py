"""Meeting dispatch visibility helpers."""

from __future__ import annotations

from typing import Any, Mapping


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _decision_payload(item: Any) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "intent_id": getattr(item, "intent_id", None),
            "reason": getattr(item, "reason", None),
        }.items()
        if value not in (None, "")
    }


def build_gate_visibility(
    gate_result: Any,
    *,
    dispatchable_count: int,
    forced_dispatch_intent_ids: set[str] | None = None,
) -> dict[str, Any]:
    forced_ids = sorted(forced_dispatch_intent_ids or set())
    return {
        "milestone": "dispatch_gate_evaluated",
        "dispatchable_count": int(dispatchable_count),
        "dispatch_intent_ids": list(getattr(gate_result, "dispatch_intents", []) or []),
        "clarify": [
            _decision_payload(item)
            for item in _as_list(getattr(gate_result, "clarify_intents", []))
        ],
        "deferred": [
            _decision_payload(item)
            for item in _as_list(getattr(gate_result, "deferred_intents", []))
        ],
        "shrunk": [
            _decision_payload(item)
            for item in _as_list(getattr(gate_result, "shrunk_intents", []))
        ],
        "forced_dispatch_intent_ids": forced_ids,
    }


def build_ir_compile_visibility(
    compiled_ir: Any,
    *,
    decomposed_phases: Any = None,
    plan_only_no_actuator: bool = False,
) -> dict[str, Any]:
    phases = list(getattr(compiled_ir, "phases", []) or []) if compiled_ir else []
    return {
        "milestone": "task_ir_compiled" if compiled_ir else "task_ir_compile_failed",
        "phase_count": len(phases),
        "phase_ids": [str(getattr(phase, "id", "")) for phase in phases if getattr(phase, "id", None)],
        "decomposed_phase_count": len(decomposed_phases or []),
        "plan_only_no_actuator": bool(plan_only_no_actuator),
    }


def build_dispatch_result_visibility(dispatch_result: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dispatch_result if isinstance(dispatch_result, Mapping) else {}
    return {
        "milestone": "dispatch_result_recorded",
        "status": result.get("status"),
        "total": result.get("total"),
        "succeeded": result.get("succeeded"),
        "failed": result.get("failed"),
        "skipped": result.get("skipped"),
    }


def record_dispatch_visibility(session: Any, visibility: Mapping[str, Any]) -> None:
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return
    current = metadata.get("dispatch_visibility")
    entries = list(current) if isinstance(current, list) else []
    entries.append(dict(visibility))
    metadata["dispatch_visibility"] = entries[-20:]
