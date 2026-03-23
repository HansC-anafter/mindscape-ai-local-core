from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _strip_ig_vision_runtime_fields(inputs: Dict[str, Any]) -> Dict[str, Any]:
    resolved = dict(inputs)
    resolved.pop("vision_execution_backend", None)
    resolved.pop("vision_target_device_id", None)
    resolved.pop("_remote_tool_routes", None)
    return resolved


def resolve_task_inputs_for_execution(
    task: Any,
    inputs: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    base_inputs: Dict[str, Any] = dict(inputs) if isinstance(inputs, dict) else {}
    intent = base_inputs.get("workload_execution_intent")
    if not isinstance(intent, dict):
        return base_inputs

    intent_kind = str(intent.get("kind") or "").strip()
    if intent_kind != "ig.vision_analyze":
        return base_inputs

    workspace_id = (
        str(getattr(task, "workspace_id", "") or "").strip()
        or str(base_inputs.get("workspace_id") or "").strip()
        or str(intent.get("workspace_id") or "").strip()
    )
    if not workspace_id:
        return base_inputs

    try:
        from capabilities.ig.services.vision_runtime_policy import (
            resolve_reference_execution_intent,
        )

        resolved_runtime = resolve_reference_execution_intent(
            intent,
            workspace_id=workspace_id,
        )
    except Exception:
        logger.warning(
            "Failed to resolve workload execution intent for task %s",
            getattr(task, "id", None) or getattr(task, "execution_id", None),
            exc_info=True,
        )
        return base_inputs

    return {
        **_strip_ig_vision_runtime_fields(base_inputs),
        **resolved_runtime,
    }
