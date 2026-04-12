from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from backend.app.models.runtime_execution_intent import (
    BindingMode,
    ExecutionBackend,
    PolicyMode,
    ResolutionMode,
    WorkloadExecutionIntent,
)
from capabilities.ig.services.workspace_storage import WorkspaceStorage

logger = logging.getLogger(__name__)

VISION_RUNTIME_POLICY_FILENAME = "vision_runtime_policy.json"
VISION_EXECUTION_INTENT_KIND = "ig.vision_analyze"
DEFAULT_VISION_EXECUTION_MODE = "local"


def _build_preference_ref(workspace_id: Optional[str]) -> Optional[str]:
    normalized = str(workspace_id or "").strip()
    if not normalized:
        return None
    return f"ig.vision.runtime_policy:{normalized}"


def normalize_vision_execution_mode(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if raw in {"remote", "cloud", "vm", "gpu"}:
        return "cloud"
    return "local"


def normalize_reference_execution_backend(value: Optional[str]) -> str:
    return (
        "remote"
        if normalize_vision_execution_mode(value) == "cloud"
        else "local"
    )


def normalize_reference_target_device_id(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip()
    return normalized or None


def _parse_float_env(name: str, default: float) -> float:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        logger.warning("[ig.vision_runtime_policy] Invalid float for %s=%s", name, raw)
        return default


def _policy_path(workspace_id: str):
    storage = WorkspaceStorage(workspace_id, "ig")
    return storage.get_config_path() / VISION_RUNTIME_POLICY_FILENAME


def load_workspace_vision_runtime_policy(workspace_id: str) -> Dict[str, Any]:
    path = _policy_path(workspace_id)
    if not path.exists():
        return {
            "vision_execution_mode": DEFAULT_VISION_EXECUTION_MODE,
            "vision_target_device_id": None,
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "[ig.vision_runtime_policy] Failed to parse %s",
            path,
            exc_info=True,
        )
        payload = {}

    return {
        "vision_execution_mode": normalize_vision_execution_mode(
            str(payload.get("vision_execution_mode") or "")
        ),
        "vision_target_device_id": normalize_reference_target_device_id(
            str(payload.get("vision_target_device_id") or "")
            if payload.get("vision_target_device_id") is not None
            else None
        ),
    }


def save_workspace_vision_runtime_policy(
    workspace_id: str,
    *,
    vision_execution_mode: Optional[str] = None,
    vision_target_device_id: Optional[str] = None,
) -> Dict[str, Any]:
    policy = {
        "vision_execution_mode": normalize_vision_execution_mode(
            vision_execution_mode or DEFAULT_VISION_EXECUTION_MODE
        ),
        "vision_target_device_id": normalize_reference_target_device_id(
            vision_target_device_id
        ),
    }
    path = _policy_path(workspace_id)
    path.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return policy


def build_reference_execution_intent(
    *,
    workspace_id: Optional[str] = None,
    vision_execution_backend: Optional[str] = None,
    vision_target_device_id: Optional[str] = None,
) -> Dict[str, Any]:
    has_explicit_backend = vision_execution_backend is not None
    normalized_target_device_id = normalize_reference_target_device_id(
        vision_target_device_id
    )
    if not has_explicit_backend and normalized_target_device_id:
        vision_execution_backend = "remote"
        has_explicit_backend = True

    if has_explicit_backend:
        execution_backend = normalize_reference_execution_backend(
            vision_execution_backend
        )
        deployment_scope_hint = (
            "cloud"
            if execution_backend == ExecutionBackend.REMOTE.value
            else "local"
        )
        policy_mode = (
            PolicyMode.CLOUD_REQUIRED.value
            if execution_backend == ExecutionBackend.REMOTE.value
            else PolicyMode.LOCAL_REQUIRED.value
        )
        return WorkloadExecutionIntent(
            workload_kind=VISION_EXECUTION_INTENT_KIND,
            kind=VISION_EXECUTION_INTENT_KIND,
            resolution_mode=ResolutionMode.FIXED.value,
            policy_mode=policy_mode,
            binding_mode=BindingMode.LIVE_PROFILE_BINDING.value,
            deployment_scope_hint=deployment_scope_hint,
            capability_profile="vision",
            logical_target="ig_vision",
            execution_backend=execution_backend,
            target_device_id=normalized_target_device_id,
            workspace_id=str(workspace_id).strip() if workspace_id else None,
            preference_ref=_build_preference_ref(workspace_id),
        ).to_payload()

    return WorkloadExecutionIntent(
        workload_kind=VISION_EXECUTION_INTENT_KIND,
        kind=VISION_EXECUTION_INTENT_KIND,
        resolution_mode=ResolutionMode.LIVE_WORKSPACE_POLICY.value,
        policy_mode=PolicyMode.PORTABLE.value,
        binding_mode=BindingMode.LIVE_PROFILE_BINDING.value,
        capability_profile="vision",
        logical_target="ig_vision",
        workspace_id=str(workspace_id).strip() if workspace_id else None,
        preference_ref=_build_preference_ref(workspace_id),
        meta={"source": "workspace_runtime_policy"},
    ).to_payload()


def normalize_reference_execution_intent_payload(
    intent: Optional[Dict[str, Any]],
    *,
    workspace_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    model = WorkloadExecutionIntent.from_payload(
        intent,
        fallback_workload_kind=VISION_EXECUTION_INTENT_KIND,
    )
    if model is None or model.workload_kind != VISION_EXECUTION_INTENT_KIND:
        return None

    if not model.binding_mode:
        model.binding_mode = BindingMode.LIVE_PROFILE_BINDING.value
    if not model.capability_profile:
        model.capability_profile = "vision"
    if not model.logical_target:
        model.logical_target = "ig_vision"
    normalized_workspace_id = str(workspace_id or model.workspace_id or "").strip()
    if normalized_workspace_id:
        model.workspace_id = normalized_workspace_id
    if not model.preference_ref:
        model.preference_ref = _build_preference_ref(normalized_workspace_id or None)
    if not model.resolution_mode:
        model.resolution_mode = ResolutionMode.LIVE_WORKSPACE_POLICY.value
    if (
        model.resolution_mode == ResolutionMode.FIXED.value
        and not model.policy_mode
    ):
        backend = normalize_reference_execution_backend(model.execution_backend)
        model.policy_mode = (
            PolicyMode.CLOUD_REQUIRED.value
            if backend == ExecutionBackend.REMOTE.value
            else PolicyMode.LOCAL_REQUIRED.value
        )
    return model.to_payload()


def extract_reference_execution_intent_from_inputs(
    inputs: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(inputs, dict):
        return None

    intent = inputs.get("workload_execution_intent")
    if isinstance(intent, dict):
        normalized_intent = normalize_reference_execution_intent_payload(
            intent,
            workspace_id=str(inputs.get("workspace_id") or "").strip() or None,
        )
        if isinstance(normalized_intent, dict):
            return normalized_intent
    return None


def _build_reference_remote_tool_routes(
    *,
    target_device_id: Optional[str] = None,
) -> Dict[str, Any]:
    route: Dict[str, Any] = {
        "execution_backend": "remote",
        "job_type": "tool",
        "tool_name": "core_llm.multimodal_analyze",
        "capability_code": "core_llm",
        "timeout_seconds": _parse_float_env(
            "IG_ANALYZE_VISION_TIMEOUT_SECONDS",
            900.0,
        ),
        "poll_interval_seconds": _parse_float_env(
            "IG_ANALYZE_VISION_POLL_INTERVAL_SECONDS",
            2.0,
        ),
    }
    normalized_target_device_id = normalize_reference_target_device_id(
        target_device_id
    )
    if normalized_target_device_id:
        route["target_device_id"] = normalized_target_device_id
    return {"vision_analyze": route}


def _build_reference_execution_resolution(
    *,
    resolved_scope: str,
    resolved_device_id: Optional[str] = None,
    route_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "resolved_scope": resolved_scope,
        "resolved_device_id": normalize_reference_target_device_id(
            resolved_device_id
        ),
    }
    if isinstance(route_metadata, dict) and route_metadata:
        payload["_remote_tool_routes"] = route_metadata
    return payload


def resolve_reference_execution_intent(
    intent: Optional[Dict[str, Any]],
    *,
    workspace_id: str,
) -> Dict[str, Any]:
    normalized_intent = normalize_reference_execution_intent_payload(
        intent,
        workspace_id=workspace_id,
    )
    if not isinstance(normalized_intent, dict):
        intent = build_reference_execution_intent(workspace_id=workspace_id)
        normalized_intent = normalize_reference_execution_intent_payload(
            intent,
            workspace_id=workspace_id,
        ) or intent

    intent = normalized_intent

    resolution_mode = str(intent.get("resolution_mode") or "").strip().lower()
    if resolution_mode == ResolutionMode.FIXED.value:
        backend_source = (
            intent.get("execution_backend")
            or intent.get("deployment_scope_hint")
            or ""
        )
        execution_backend = normalize_reference_execution_backend(
            str(backend_source)
        )
        target_device_id = normalize_reference_target_device_id(
            str(intent.get("target_device_id") or "")
            if intent.get("target_device_id") is not None
            else None
        )
        if execution_backend == ExecutionBackend.REMOTE.value:
            return _build_reference_execution_resolution(
                resolved_scope="cloud",
                resolved_device_id=target_device_id,
                route_metadata=_build_reference_remote_tool_routes(
                    target_device_id=target_device_id
                ),
            )
        return _build_reference_execution_resolution(resolved_scope="local")

    policy = load_workspace_vision_runtime_policy(workspace_id)
    target_device_id = normalize_reference_target_device_id(
        policy.get("vision_target_device_id")
    )
    if normalize_vision_execution_mode(policy.get("vision_execution_mode")) == "cloud":
        return _build_reference_execution_resolution(
            resolved_scope="cloud",
            resolved_device_id=target_device_id,
            route_metadata=_build_reference_remote_tool_routes(
                target_device_id=target_device_id
            ),
        )
    return _build_reference_execution_resolution(resolved_scope="local")
