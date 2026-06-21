from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.models.runtime_execution_intent import (
    ExecutionBackend,
    PolicyMode,
    WorkloadExecutionIntent,
)


logger = logging.getLogger("backend.app.services.execution_intent_resolver")


def normalize_optional_string(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    return normalized or None


def extract_workload_execution_intent_model(
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


def should_use_render_control_plane_preflight(
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


def should_park_on_control_plane_unavailable(
    intent_model: Optional[WorkloadExecutionIntent],
) -> bool:
    if intent_model is None:
        return False
    return (
        str(intent_model.policy_mode or "").strip().lower()
        == PolicyMode.CLOUD_REQUIRED.value
    )


def extract_route_metadata(inputs: Dict[str, Any]) -> Dict[str, Any]:
    routes = inputs.get("_remote_tool_routes")
    if not isinstance(routes, dict):
        routes = inputs.get("remote_tool_routes")
    return dict(routes) if isinstance(routes, dict) else {}


def has_prebuilt_remote_routes(inputs: Dict[str, Any]) -> bool:
    return bool(extract_route_metadata(inputs))


class WorkloadIntentMixin:
    @staticmethod
    def _normalize_optional_string(value: Optional[str]) -> Optional[str]:
        return normalize_optional_string(value)

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
    def _extract_route_metadata(inputs: Dict[str, Any]) -> Dict[str, Any]:
        return extract_route_metadata(inputs)

    @classmethod
    def _has_prebuilt_remote_routes(cls, inputs: Dict[str, Any]) -> bool:
        return bool(cls._extract_route_metadata(inputs))
