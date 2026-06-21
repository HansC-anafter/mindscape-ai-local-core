from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from backend.app.models.runtime_execution_intent import WorkloadExecutionIntent
from backend.app.services.execution_intent_resolver_core.types import (
    ExecutionIntentResolution,
)
from backend.app.services.execution_intent_resolver_core.workload import (
    normalize_optional_string,
)

if TYPE_CHECKING:
    from backend.app.models.workspace import Task


logger = logging.getLogger("backend.app.services.execution_intent_resolver")


def extract_ig_reference_execution_intent(
    raw_inputs: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    from backend.app.capabilities.ig.services.vision_runtime_policy import (
        extract_reference_execution_intent_from_inputs,
    )

    return extract_reference_execution_intent_from_inputs(raw_inputs)


def resolve_ig_reference_execution_intent(
    intent: Optional[Dict[str, Any]],
    *,
    workspace_id: str,
) -> Dict[str, Any]:
    from backend.app.capabilities.ig.services.vision_runtime_policy import (
        resolve_reference_execution_intent,
    )

    return resolve_reference_execution_intent(intent, workspace_id=workspace_id)


class IGReferenceIntentResolverMixin:
    def _resolve_ig_reference_intent(
        self,
        *,
        task: "Task",
        execution_context: Optional[Dict[str, Any]],
        raw_inputs: Dict[str, Any],
        intent_model: Optional[WorkloadExecutionIntent],
    ) -> Optional[ExecutionIntentResolution]:
        if (
            intent_model is not None
            and str(intent_model.workload_kind or "").strip() != "ig.vision_analyze"
        ):
            return None

        try:
            intent = extract_ig_reference_execution_intent(raw_inputs)
        except Exception:
            logger.warning(
                "ExecutionIntentResolver: failed to extract IG reference execution intent "
                "for task %s",
                getattr(task, "id", None),
                exc_info=True,
            )
            return None

        if not isinstance(intent, dict):
            return None

        ctx = execution_context if isinstance(execution_context, dict) else {}
        workspace_id = str(
            raw_inputs.get("workspace_id")
            or ctx.get("workspace_id")
            or getattr(task, "workspace_id", "")
            or ""
        ).strip()
        if not workspace_id:
            logger.warning(
                "ExecutionIntentResolver: missing workspace_id for IG intent on task %s",
                getattr(task, "id", None),
            )
            return None

        resolved = resolve_ig_reference_execution_intent(
            intent,
            workspace_id=workspace_id,
        )
        if not isinstance(resolved, dict):
            return None

        effective_inputs = dict(raw_inputs)
        effective_inputs["workload_execution_intent"] = dict(intent)
        route_metadata = (
            dict(resolved.get("_remote_tool_routes"))
            if isinstance(resolved.get("_remote_tool_routes"), dict)
            else {}
        )
        if route_metadata:
            effective_inputs["_remote_tool_routes"] = route_metadata
        else:
            effective_inputs.pop("_remote_tool_routes", None)
            effective_inputs.pop("remote_tool_routes", None)

        resolved_scope = normalize_optional_string(
            resolved.get("resolved_scope")
        ) or "local"
        resolved_device_id = normalize_optional_string(
            resolved.get("resolved_device_id")
        )
        effective_inputs["_resolved_workload_scope"] = resolved_scope
        if resolved_device_id:
            effective_inputs["_resolved_target_device_id"] = resolved_device_id
        else:
            effective_inputs.pop("_resolved_target_device_id", None)

        for legacy_key in (
            "vision_execution_backend",
            "vision_target_device_id",
            "_ig_vision_execution_backend",
            "_ig_vision_target_device_id",
        ):
            effective_inputs.pop(legacy_key, None)

        if resolved_scope == "local":
            effective_inputs.pop("_remote_tool_routes", None)
            effective_inputs.pop("remote_tool_routes", None)
            route_metadata = {}
            resolved_device_id = None

        return ExecutionIntentResolution(
            effective_inputs=effective_inputs,
            effective_route_metadata=route_metadata,
            resolved_scope=resolved_scope,
            resolved_device_id=(
                str(resolved_device_id).strip() if resolved_device_id else None
            ),
        )
