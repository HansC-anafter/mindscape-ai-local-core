from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.models.runtime_execution_intent import (
    BindingMode,
    WorkloadExecutionIntent,
)
from backend.app.services.execution_intent_resolver_core.control_plane import (
    detect_runtime_block_reason,
    normalize_control_plane_site_key,
    probe_control_plane_runtime_availability,
)
from backend.app.services.execution_intent_resolver_core.types import (
    ExecutionIntentResolution,
)
from backend.app.services.execution_intent_resolver_core.workload import (
    should_park_on_control_plane_unavailable,
    should_use_render_control_plane_preflight,
)


class GenericFrozenSnapshotResolverMixin:
    def _resolve_generic_frozen_snapshot_intent(
        self,
        *,
        raw_inputs: Dict[str, Any],
        intent_model: Optional[WorkloadExecutionIntent],
    ) -> Optional[ExecutionIntentResolution]:
        if intent_model is None:
            return None
        binding_mode = str(intent_model.binding_mode or "").strip().lower()
        if binding_mode != BindingMode.FROZEN_WORKLOAD_SNAPSHOT.value:
            return None

        effective_inputs = dict(raw_inputs)
        effective_inputs["workload_execution_intent"] = intent_model.to_payload()
        if isinstance(raw_inputs.get("workload_snapshot"), dict):
            effective_inputs["workload_snapshot"] = dict(raw_inputs["workload_snapshot"])

        resolved_scope = self._resolve_scope(intent_model)
        resolved_device_id = self._normalize_optional_string(
            intent_model.target_device_id
        )
        route_metadata = self._build_generic_remote_route_metadata(
            intent_model=intent_model,
            resolved_scope=resolved_scope,
            resolved_device_id=resolved_device_id,
        )

        control_plane_availability = None
        if should_use_render_control_plane_preflight(
            intent_model=intent_model,
            resolved_scope=resolved_scope,
            route_metadata=route_metadata,
        ):
            control_plane_availability = probe_control_plane_runtime_availability(
                site_key=normalize_control_plane_site_key(intent_model),
                target_device_id=resolved_device_id,
            )
            selected_device_id = None
            if isinstance(control_plane_availability, dict):
                selected_device_id = self._normalize_optional_string(
                    control_plane_availability.get("selected_device_id")
                )
            if selected_device_id and not resolved_device_id:
                resolved_device_id = selected_device_id
                route_metadata = self._build_generic_remote_route_metadata(
                    intent_model=intent_model,
                    resolved_scope=resolved_scope,
                    resolved_device_id=resolved_device_id,
                )

        if resolved_scope:
            effective_inputs["_resolved_workload_scope"] = resolved_scope
        else:
            effective_inputs.pop("_resolved_workload_scope", None)

        if resolved_device_id:
            effective_inputs["_resolved_target_device_id"] = resolved_device_id
        else:
            effective_inputs.pop("_resolved_target_device_id", None)

        if route_metadata:
            effective_inputs["_remote_tool_routes"] = route_metadata
        else:
            effective_inputs.pop("_remote_tool_routes", None)

        runtime_block_reason = detect_runtime_block_reason(
            intent_model=intent_model,
            resolved_scope=resolved_scope,
            route_metadata=route_metadata,
        )
        if runtime_block_reason:
            blocked_payload = {
                "required_scope": resolved_scope,
                "policy_mode": self._normalize_optional_string(intent_model.policy_mode),
                "logical_target": self._normalize_optional_string(intent_model.logical_target),
                "site_key": self._normalize_optional_string(intent_model.site_key),
                "target_device_id": resolved_device_id,
            }
            if isinstance(runtime_block_reason, dict):
                reason_code = self._normalize_optional_string(
                    runtime_block_reason.get("reason_code")
                ) or "runtime_unavailable"
                blocked_payload["reason_code"] = reason_code
                for key, value in runtime_block_reason.items():
                    if key == "reason_code":
                        continue
                    normalized_value = self._normalize_optional_string(value)
                    if normalized_value is not None:
                        blocked_payload[key] = normalized_value
            else:
                blocked_payload["reason_code"] = str(runtime_block_reason)
            return ExecutionIntentResolution(
                effective_inputs=effective_inputs,
                effective_route_metadata=route_metadata,
                park_task=True,
                blocked_reason="runtime_unavailable",
                blocked_payload=blocked_payload,
                resolved_scope=resolved_scope,
                resolved_device_id=resolved_device_id,
            )

        if (
            isinstance(control_plane_availability, dict)
            and control_plane_availability.get("available") is False
            and should_park_on_control_plane_unavailable(intent_model)
        ):
            blocked_payload = {
                "reason_code": self._normalize_optional_string(
                    control_plane_availability.get("reason_code")
                )
                or "no_runtime_available",
                "required_scope": resolved_scope,
                "policy_mode": self._normalize_optional_string(intent_model.policy_mode),
                "logical_target": self._normalize_optional_string(intent_model.logical_target),
                "site_key": self._normalize_optional_string(
                    control_plane_availability.get("site_key")
                )
                or self._normalize_optional_string(intent_model.site_key),
                "target_device_id": resolved_device_id,
                "availability_source": "site_hub_control_plane",
            }
            requested_device_id = self._normalize_optional_string(
                control_plane_availability.get("requested_device_id")
            )
            selected_device_id = self._normalize_optional_string(
                control_plane_availability.get("selected_device_id")
            )
            if requested_device_id is not None:
                blocked_payload["requested_device_id"] = requested_device_id
            if selected_device_id is not None:
                blocked_payload["selected_device_id"] = selected_device_id
            return ExecutionIntentResolution(
                effective_inputs=effective_inputs,
                effective_route_metadata=route_metadata,
                park_task=True,
                blocked_reason="runtime_unavailable",
                blocked_payload=blocked_payload,
                resolved_scope=resolved_scope,
                resolved_device_id=resolved_device_id,
            )

        return ExecutionIntentResolution(
            effective_inputs=effective_inputs,
            effective_route_metadata=route_metadata,
            resolved_scope=resolved_scope,
            resolved_device_id=resolved_device_id,
        )
