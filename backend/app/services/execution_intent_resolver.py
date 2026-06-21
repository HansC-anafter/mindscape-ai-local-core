from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from backend.app.services.execution_intent_resolver_core import (
    ExecutionIntentResolution,
    GenericFrozenSnapshotResolverMixin,
    IGReferenceIntentResolverMixin,
    WorkloadIntentMixin,
    detect_runtime_block_reason as _detect_runtime_block_reason,
    extract_ig_reference_execution_intent as _extract_ig_reference_execution_intent,
    extract_route_metadata as _extract_route_metadata,
    extract_workload_execution_intent_model as _extract_workload_execution_intent_model,
    has_prebuilt_remote_routes as _has_prebuilt_remote_routes,
    inspect_cloud_connector_connected_state as _inspect_cloud_connector_connected_state,
    normalize_control_plane_site_key as _normalize_control_plane_site_key,
    normalize_optional_string as _normalize_optional_string,
    probe_control_plane_runtime_availability as _probe_control_plane_runtime_availability,
    resolve_execution_control_api_base as _resolve_execution_control_api_base,
    resolve_ig_reference_execution_intent as _resolve_ig_reference_execution_intent,
    should_park_on_control_plane_unavailable as _should_park_on_control_plane_unavailable,
    should_use_render_control_plane_preflight as _should_use_render_control_plane_preflight,
)

if TYPE_CHECKING:
    from backend.app.models.workspace import Task


class ExecutionIntentResolver(
    IGReferenceIntentResolverMixin,
    GenericFrozenSnapshotResolverMixin,
    WorkloadIntentMixin,
):
    """Resolve workload intent into effective execution inputs at run attempt time."""

    def resolve(
        self,
        *,
        task: "Task",
        execution_context: Optional[Dict[str, Any]],
        raw_inputs: Optional[Dict[str, Any]],
    ) -> ExecutionIntentResolution:
        effective_inputs = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
        if not effective_inputs:
            return ExecutionIntentResolution(effective_inputs={})

        if self._has_prebuilt_remote_routes(effective_inputs):
            return ExecutionIntentResolution(
                effective_inputs=effective_inputs,
                effective_route_metadata=self._extract_route_metadata(effective_inputs),
            )

        intent_model = _extract_workload_execution_intent_model(effective_inputs)

        generic_resolution = self._resolve_generic_frozen_snapshot_intent(
            raw_inputs=effective_inputs,
            intent_model=intent_model,
        )
        if generic_resolution is not None:
            return generic_resolution

        ig_resolution = self._resolve_ig_reference_intent(
            task=task,
            execution_context=execution_context,
            raw_inputs=effective_inputs,
            intent_model=intent_model,
        )
        if ig_resolution is not None:
            return ig_resolution

        return ExecutionIntentResolution(effective_inputs=effective_inputs)
