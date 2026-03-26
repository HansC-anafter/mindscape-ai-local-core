from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.models.runtime_execution_intent import (
    BindingMode,
    ExecutionBackend,
    PolicyMode,
    WorkloadExecutionIntent,
)
from backend.app.utils.cloud_integration import get_cloud_integration_api_base

if TYPE_CHECKING:
    from backend.app.models.workspace import Task


logger = logging.getLogger(__name__)


@dataclass
class ExecutionIntentResolution:
    effective_inputs: Dict[str, Any]
    effective_route_metadata: Dict[str, Any] = field(default_factory=dict)
    park_task: bool = False
    blocked_reason: Optional[str] = None
    blocked_payload: Optional[Dict[str, Any]] = None
    resolved_scope: Optional[str] = None
    resolved_device_id: Optional[str] = None


def _extract_ig_reference_execution_intent(
    raw_inputs: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    from backend.app.capabilities.ig.services.vision_runtime_policy import (
        extract_reference_execution_intent_from_inputs,
    )

    return extract_reference_execution_intent_from_inputs(raw_inputs)


def _resolve_ig_reference_execution_intent(
    intent: Optional[Dict[str, Any]],
    *,
    workspace_id: str,
) -> Dict[str, Any]:
    from backend.app.capabilities.ig.services.vision_runtime_policy import (
        resolve_reference_execution_intent,
    )

    return resolve_reference_execution_intent(intent, workspace_id=workspace_id)


def _extract_workload_execution_intent_model(
    raw_inputs: Optional[Dict[str, Any]],
) -> Optional[WorkloadExecutionIntent]:
    if not isinstance(raw_inputs, dict):
        return None
    payload = raw_inputs.get("workload_execution_intent")
    if not isinstance(payload, dict):
        return None
    try:
        return WorkloadExecutionIntent.from_payload(payload)
    except Exception:
        logger.warning(
            "ExecutionIntentResolver: failed to parse workload_execution_intent",
            exc_info=True,
        )
        return None


def _should_use_render_control_plane_preflight(
    *,
    intent_model: Optional[WorkloadExecutionIntent],
    resolved_scope: Optional[str],
    route_metadata: Optional[Dict[str, Any]],
) -> bool:
    if intent_model is None or resolved_scope != "cloud":
        return False
    if str(intent_model.logical_target or "").strip().lower() != "video_renderer_generative":
        return False
    if not isinstance(route_metadata, dict) or not route_metadata:
        return False
    return True


def _should_park_on_control_plane_unavailable(
    intent_model: Optional[WorkloadExecutionIntent],
) -> bool:
    if intent_model is None:
        return False
    return (
        str(intent_model.policy_mode or "").strip().lower()
        == PolicyMode.CLOUD_REQUIRED.value
    )


def _detect_runtime_block_reason(
    *,
    intent_model: Optional[WorkloadExecutionIntent],
    resolved_scope: Optional[str],
    route_metadata: Optional[Dict[str, Any]],
) -> Optional[str]:
    if not _should_use_render_control_plane_preflight(
        intent_model=intent_model,
        resolved_scope=resolved_scope,
        route_metadata=route_metadata,
    ):
        return None

    connected = _inspect_cloud_connector_connected_state()
    # When the app-level connector is configured but not connected yet, strict
    # cloud-required workloads would fail immediately in the workflow seam.
    if connected is False and _should_park_on_control_plane_unavailable(intent_model):
        return "cloud_connector_disconnected"
    return None


def _normalize_optional_string(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_control_plane_site_key(
    intent_model: WorkloadExecutionIntent,
) -> Optional[str]:
    return _normalize_optional_string(intent_model.site_key) or _normalize_optional_string(
        os.getenv("SITE_KEY")
    )


def _inspect_cloud_connector_connected_state() -> Optional[bool]:
    try:
        from backend.app.main import app

        connector = getattr(app.state, "cloud_connector", None)
    except Exception:
        connector = None

    if connector is None:
        return None

    try:
        is_connected = getattr(connector, "is_connected", None)
        if callable(is_connected):
            return bool(is_connected())
        return bool(is_connected)
    except Exception:
        logger.warning(
            "ExecutionIntentResolver: failed to inspect cloud connector state",
            exc_info=True,
        )
        return None


def _resolve_execution_control_api_base() -> Optional[str]:
    return (
        _normalize_optional_string(os.getenv("EXECUTION_CONTROL_API_URL"))
        or _normalize_optional_string(os.getenv("SITE_HUB_API_URL"))
        or _normalize_optional_string(os.getenv("CLOUD_API_URL"))
        or _normalize_optional_string(get_cloud_integration_api_base())
    )


def _probe_control_plane_runtime_availability(
    *,
    site_key: Optional[str],
    target_device_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    normalized_site_key = _normalize_optional_string(site_key)
    if not normalized_site_key:
        return None

    base_url = _resolve_execution_control_api_base()
    if not base_url:
        return None

    params = {"site_key": normalized_site_key}
    normalized_device_id = _normalize_optional_string(target_device_id)
    if normalized_device_id:
        params["device_id"] = normalized_device_id

    request_url = (
        f"{base_url.rstrip('/')}/api/v1/executions/availability?{urlencode(params)}"
    )
    headers: Dict[str, str] = {}
    api_key = _normalize_optional_string(os.getenv("CLOUD_API_KEY")) or _normalize_optional_string(
        os.getenv("CLOUD_PROVIDER_TOKEN")
    )
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    device_id = _normalize_optional_string(os.getenv("DEVICE_ID"))
    if device_id:
        headers["X-Device-Id"] = device_id

    try:
        with urlopen(Request(request_url, headers=headers), timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.info(
            "ExecutionIntentResolver: control-plane runtime availability probe failed for site_key=%s device_id=%s",
            normalized_site_key,
            normalized_device_id,
            exc_info=True,
        )
        return None

    if not isinstance(payload, dict):
        return None
    return payload


class ExecutionIntentResolver:
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
            intent = _extract_ig_reference_execution_intent(raw_inputs)
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

        resolved = _resolve_ig_reference_execution_intent(
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

        resolved_scope = self._normalize_optional_string(
            resolved.get("resolved_scope")
        ) or "local"
        resolved_device_id = self._normalize_optional_string(
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
        if _should_use_render_control_plane_preflight(
            intent_model=intent_model,
            resolved_scope=resolved_scope,
            route_metadata=route_metadata,
        ):
            control_plane_availability = _probe_control_plane_runtime_availability(
                site_key=_normalize_control_plane_site_key(intent_model),
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

        runtime_block_reason = _detect_runtime_block_reason(
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
            and _should_park_on_control_plane_unavailable(intent_model)
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

    @staticmethod
    def _normalize_optional_string(value: Optional[str]) -> Optional[str]:
        return _normalize_optional_string(value)

    @classmethod
    def _resolve_scope(cls, intent_model: WorkloadExecutionIntent) -> Optional[str]:
        backend = cls._normalize_optional_string(intent_model.execution_backend)
        if backend == ExecutionBackend.REMOTE.value:
            return "cloud"
        if backend == ExecutionBackend.LOCAL.value:
            return "local"

        deployment_scope_hint = cls._normalize_optional_string(
            intent_model.deployment_scope_hint
        )
        if deployment_scope_hint in {"cloud", "remote"}:
            return "cloud"
        if deployment_scope_hint == "local":
            return "local"

        policy_mode = cls._normalize_optional_string(intent_model.policy_mode)
        if policy_mode in {
            PolicyMode.CLOUD_REQUIRED.value,
            PolicyMode.PREFER_CLOUD.value,
        }:
            return "cloud"
        if policy_mode in {
            PolicyMode.LOCAL_REQUIRED.value,
            PolicyMode.PREFER_LOCAL.value,
            PolicyMode.PORTABLE.value,
        }:
            return "local"

        if cls._normalize_optional_string(intent_model.target_device_id):
            return "cloud"
        return None

    @classmethod
    def _build_generic_remote_route_metadata(
        cls,
        *,
        intent_model: WorkloadExecutionIntent,
        resolved_scope: Optional[str],
        resolved_device_id: Optional[str],
    ) -> Dict[str, Any]:
        if resolved_scope != "cloud":
            return {}

        logical_target = cls._normalize_optional_string(intent_model.logical_target)
        if logical_target != "video_renderer_generative":
            return {}

        fallback_local_on_error = bool(intent_model.allow_local_fallback)
        policy_mode = cls._normalize_optional_string(intent_model.policy_mode)
        if not fallback_local_on_error and policy_mode in {
            PolicyMode.PREFER_CLOUD.value,
            PolicyMode.PORTABLE.value,
        }:
            fallback_local_on_error = True

        route: Dict[str, Any] = {
            "execution_backend": "remote",
            "job_type": "tool",
            "tool_name": "video_renderer.vr_render_generative",
            "capability_code": "video_renderer",
            "fallback_local_on_error": fallback_local_on_error,
        }
        site_key = cls._normalize_optional_string(intent_model.site_key)
        if site_key:
            route["site_key"] = site_key
        if resolved_device_id:
            route["target_device_id"] = resolved_device_id

        return {
            "video_renderer.vr_render_generative": route,
        }

    @staticmethod
    def _has_prebuilt_remote_routes(inputs: Dict[str, Any]) -> bool:
        return bool(ExecutionIntentResolver._extract_route_metadata(inputs))

    @staticmethod
    def _extract_route_metadata(inputs: Dict[str, Any]) -> Dict[str, Any]:
        routes = inputs.get("_remote_tool_routes")
        if not isinstance(routes, dict):
            routes = inputs.get("remote_tool_routes")
        return dict(routes) if isinstance(routes, dict) else {}
