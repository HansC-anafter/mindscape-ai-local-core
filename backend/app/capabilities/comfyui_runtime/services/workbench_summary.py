from __future__ import annotations

from typing import Any, Dict, Optional

from capabilities.comfyui_runtime.services.workbench_summary_profiles import (
    _available_runtime_packages,
    _build_laf_runtime_plan as _build_laf_runtime_plan_impl,
    _build_lane_entries as _build_lane_entries_impl,
    _discover_pack_model_files,
    _failure_catalog,
    _flatten_available_model_files,
    _flatten_available_nodes,
    _laf_manifest_path,
    _lane_entry,
    _load_laf_manifest,
    _load_manifest,
    _manifest_path,
    _model_index,
    _models_storage_root,
    _profile_readiness_entries,
    _recommended_state,
)
from capabilities.comfyui_runtime.services.workbench_summary_preview_audit import (
    build_preview_runtime_audit_payload,
)
from capabilities.comfyui_runtime.services.workbench_summary_regional import (
    merge_regional_adapter_host_readiness,
)
from capabilities.comfyui_runtime.services.talking_head_runtime_plan import (
    build_talking_head_runtime_plan,
)
from capabilities.comfyui_runtime.services.regional_adapter_runtime_plan import (
    build_regional_adapter_runtime_plan,
)
from capabilities.comfyui_runtime.services.regional_adapter_runtime_install import (
    sync_regional_adapter_runtime,
)
from capabilities.comfyui_runtime.services.preview_runtime_audit import (
    sync_preview_runtime_audit,
)
from capabilities.comfyui_runtime.services.workbench_summary_runtime import (
    _build_runtime_summary as _build_runtime_summary_impl,
    _resolve_comfyui_url,
    _resolve_registered_runtime as _resolve_registered_runtime_impl,
)
from capabilities.comfyui_runtime.services.workbench_summary_runs import (
    _aggregate_review_followups,
    _canonicalize_followup_plan,
    _canonicalize_followup_request_refs,
    _default_source_ref,
    _resolve_run_compat_state,
    _review_bundle_ref,
    _scene_binding_projections,
    _scene_review_followup,
    _summarize_run,
    _summarize_scene_projection,
    get_workbench_binding,
    list_workbench_runs,
)
from capabilities.comfyui_runtime.tools.health_check import health_check
from capabilities.layer_asset_forge.services.runtime_install import build_runtime_install_plan

_WORKBENCH_SUMMARY_SCHEMA_VERSION = "comfyui_runtime.workbench.summary.v1"
_WORKBENCH_PROFILES_SCHEMA_VERSION = "comfyui_runtime.workbench.profiles.v1"
_WORKBENCH_RUNTIME_HEALTH_SCHEMA_VERSION = "comfyui_runtime.workbench.runtime_health.v1"


def _build_laf_runtime_plan() -> Dict[str, Any]:
    return _build_laf_runtime_plan_impl(build_runtime_install_plan)


async def _resolve_registered_runtime() -> Dict[str, Any]:
    return await _resolve_registered_runtime_impl()


def _build_runtime_summary(comfyui_url: str) -> Dict[str, Any]:
    return _build_runtime_summary_impl(
        comfyui_url,
        health_check_fn=health_check,
    )


def _runtime_ref_for_health(runtime_ref: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(runtime_ref)
    payload.pop("runtime_snapshot", None)
    return payload


def _build_preview_runtime_audit_payload() -> Dict[str, Any]:
    return build_preview_runtime_audit_payload(sync_preview_runtime_audit)


def _merge_regional_adapter_host_readiness(
    *,
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    return merge_regional_adapter_host_readiness(
        plan=plan,
        sync_regional_adapter_runtime_fn=sync_regional_adapter_runtime,
    )


def _build_lane_entries(
    *,
    comfy_manifest: Dict[str, Any],
    laf_manifest: Dict[str, Any],
    runtime_snapshot: Optional[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    return _build_lane_entries_impl(
        comfy_manifest=comfy_manifest,
        laf_manifest=laf_manifest,
        runtime_snapshot=runtime_snapshot,
        build_laf_runtime_plan_fn=_build_laf_runtime_plan,
    )


async def build_workbench_summary(
    *,
    tenant_id: str,
    project_id: Optional[str] = None,
    comfyui_url: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    manifest = _load_manifest()
    registered_runtime = await _resolve_registered_runtime()
    resolved_url = _resolve_comfyui_url(
        requested_url=comfyui_url,
        registered_runtime=registered_runtime,
    )
    runtime = _build_runtime_summary(resolved_url)
    profiles = _profile_readiness_entries(
        manifest=manifest,
        runtime_snapshot=runtime.get("runtime_snapshot"),
    )
    recent_runs = (
        list_workbench_runs(
            tenant_id=tenant_id,
            project_id=project_id,
            limit=limit,
        )
        if project_id
        else []
    )

    return {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "contract": {
            "schema_version": _WORKBENCH_SUMMARY_SCHEMA_VERSION,
            "compat_state": "source_record_only",
            "narrative_state": "inspection_ready",
            "dispatch_source_policy": "source_record_only",
        },
        "runtime": {
            **registered_runtime,
            **runtime,
        },
        "profiles": profiles,
        "recent_runs": recent_runs,
    }


async def build_workbench_profiles(
    *,
    tenant_id: str,
    comfyui_url: Optional[str] = None,
) -> Dict[str, Any]:
    comfy_manifest = _load_manifest()
    laf_manifest = _load_laf_manifest()
    registered_runtime = await _resolve_registered_runtime()
    resolved_url = _resolve_comfyui_url(
        requested_url=comfyui_url,
        registered_runtime=registered_runtime,
    )
    runtime = _build_runtime_summary(resolved_url)
    runtime_snapshot = runtime.get("runtime_snapshot")
    profiles = _profile_readiness_entries(
        manifest=comfy_manifest,
        runtime_snapshot=runtime_snapshot,
    )
    laf_runtime_plan = _build_laf_runtime_plan()
    lanes = _build_lane_entries(
        comfy_manifest=comfy_manifest,
        laf_manifest=laf_manifest,
        runtime_snapshot=runtime_snapshot,
    )
    return {
        "tenant_id": tenant_id,
        "contract": {
            "schema_version": _WORKBENCH_PROFILES_SCHEMA_VERSION,
            "narrative_state": "inspection_ready",
            "dispatch_source_policy": "source_record_only",
        },
        "runtime_ref": {
            **registered_runtime,
            **runtime,
        },
        "laf_runtime": {
            "pack_code": laf_runtime_plan.get("pack_code"),
            "install_target": laf_runtime_plan.get("install_target"),
            "isolation_mode": laf_runtime_plan.get("isolation_mode"),
            "narrative_state": laf_runtime_plan.get("narrative_state"),
            "readiness_state": laf_runtime_plan.get("readiness_state"),
            "host_bridge_state": laf_runtime_plan.get("host_bridge_state"),
            "runtime_root": laf_runtime_plan.get("runtime_root"),
            "venv_path": laf_runtime_plan.get("venv_path"),
            "python_executable": laf_runtime_plan.get("python_executable"),
            "torch_backend": laf_runtime_plan.get("torch_backend"),
            "compose_baseline_required": laf_runtime_plan.get("compose_baseline_required"),
            "mutates_shared_runtime": laf_runtime_plan.get("mutates_shared_runtime"),
            "isolated_runtime_supported": laf_runtime_plan.get("isolated_runtime_supported"),
            "auto_pip_runtime_specs": list(laf_runtime_plan.get("auto_pip_runtime_specs") or []),
            "source_install_specs": list(laf_runtime_plan.get("source_install_specs") or []),
            "manual_only_specs": list(laf_runtime_plan.get("manual_only_specs") or []),
            "auto_pip_packages": list(
                laf_runtime_plan.get("auto_pip_packages")
                or laf_runtime_plan.get("installable_python_packages")
                or []
            ),
            "installable_python_packages": list(
                laf_runtime_plan.get("installable_python_packages") or []
            ),
            "missing_runtime_install_specs": list(
                laf_runtime_plan.get("missing_runtime_install_specs") or []
            ),
            "missing_model_weight_ids": list(
                laf_runtime_plan.get("missing_model_weight_ids") or []
            ),
            "install_command_preview": list(
                laf_runtime_plan.get("install_command_preview") or []
            ),
            "endpoint": "/api/v1/capabilities/layer_asset_forge/runtime/plan",
        },
        "profiles": profiles,
        "lanes": lanes,
    }


async def build_runtime_health(
    *,
    tenant_id: str,
    comfyui_url: Optional[str] = None,
) -> Dict[str, Any]:
    profiles_payload = await build_workbench_profiles(
        tenant_id=tenant_id,
        comfyui_url=comfyui_url,
    )
    runtime_ref = dict(profiles_payload.get("runtime_ref") or {})
    laf_runtime = dict(profiles_payload.get("laf_runtime") or {})
    lanes = list(profiles_payload.get("lanes") or [])
    profiles = list(profiles_payload.get("profiles") or [])
    lane_by_id = {
        str(lane.get("lane_id") or "").strip(): lane
        for lane in lanes
        if isinstance(lane, dict)
    }

    registration_state = str(runtime_ref.get("registration_state") or "unknown").strip()
    live_health_state = str(runtime_ref.get("live_status") or "error").strip()
    if registration_state != "registered":
        dispatch_state = "registration_required"
    elif live_health_state != "ok":
        dispatch_state = "live_unavailable"
    else:
        dispatch_state = "ready"

    object_selection_lane = lane_by_id.get("object_selection_mask_proposal", {})
    object_render_lane = lane_by_id.get("object_render", {})
    talking_head_lane = lane_by_id.get("hybrid_talking_head_preview", {})
    regional_multi_subject_lane = lane_by_id.get(
        "regional_multi_subject_preview",
        {},
    )
    flux2_klein_true_v2_q6_lane = lane_by_id.get(
        "flux2_klein_true_v2_q6_local",
        {},
    )
    preview_profile = next(
        (profile for profile in profiles if profile.get("profile_id") == "vr_preview_local"),
        {},
    )
    recommended_for = {
        "scene_preview": "ready" if preview_profile.get("ready") else "blocked",
        "object_extract": _recommended_state(lane=object_selection_lane),
        "object_render": (
            "ready"
            if list(object_render_lane.get("ready_profile_ids") or [])
            else _recommended_state(lane=object_render_lane)
        ),
        "multi_subject_preview": _recommended_state(
            lane=regional_multi_subject_lane
        ),
        "flux2_klein_true_v2_q6_preview": _recommended_state(
            lane=flux2_klein_true_v2_q6_lane
        ),
        "talking_head_preview": _recommended_state(lane=talking_head_lane),
    }

    active_failures: list[str] = []
    if str(object_selection_lane.get("ready_verdict") or "").strip() != "ready":
        active_failures.append("mask_missing")
    if str(object_render_lane.get("ready_verdict") or "").strip() in {
        "missing_nodes",
        "missing_models",
    }:
        active_failures.append("renderer_slot_incompatible")
    regional_multi_subject_ready_verdict = str(
        regional_multi_subject_lane.get("ready_verdict") or ""
    ).strip()
    if regional_multi_subject_ready_verdict and regional_multi_subject_ready_verdict != "ready":
        active_failures.append("regional_multi_subject_runtime_unavailable")
    flux2_klein_true_v2_q6_ready_verdict = str(
        flux2_klein_true_v2_q6_lane.get("ready_verdict") or ""
    ).strip()
    if (
        flux2_klein_true_v2_q6_ready_verdict
        and flux2_klein_true_v2_q6_ready_verdict != "ready"
    ):
        active_failures.append("flux2_klein_true_v2_q6_runtime_unavailable")
    talking_head_install_action_state = str(
        talking_head_lane.get("install_action_state") or ""
    ).strip()
    talking_head_ready_verdict = str(
        talking_head_lane.get("ready_verdict") or ""
    ).strip()
    if talking_head_install_action_state == "blocked_configuration":
        active_failures.append("talking_head_runtime_config_incomplete")
    elif talking_head_install_action_state in {
        "manual_only",
        "manual_only_required",
    }:
        active_failures.append("talking_head_runtime_manual_only")
    elif talking_head_ready_verdict and talking_head_ready_verdict != "ready":
        active_failures.append("talking_head_runtime_unavailable")

    preview_runtime_audit = _build_preview_runtime_audit_payload()

    return {
        "tenant_id": tenant_id,
        "contract": {
            "schema_version": _WORKBENCH_RUNTIME_HEALTH_SCHEMA_VERSION,
            "narrative_state": "gatekeeper_ready",
            "dispatch_source_policy": "source_record_only",
        },
        "registration_state": registration_state,
        "live_health_state": live_health_state,
        "dispatch_state": dispatch_state,
        "recommended_for": recommended_for,
        "lane_verdicts": {
            lane_id: lane.get("ready_verdict")
            for lane_id, lane in lane_by_id.items()
        },
        "active_failures": active_failures,
        "failure_catalog": _failure_catalog(),
        "runtime_ref": _runtime_ref_for_health(runtime_ref),
        "laf_runtime": laf_runtime,
        "preview_runtime_audit": preview_runtime_audit,
        "dependency_conflicts": preview_runtime_audit.get("dependency_conflicts") or [],
        "python_env": preview_runtime_audit.get("python_env") or {},
        "process_profiles": preview_runtime_audit.get("process_profiles") or [],
        "shared_venv_risk": preview_runtime_audit.get("shared_venv_risk") or {},
        "kimodo_preflight": preview_runtime_audit.get("kimodo_preflight") or {},
        "kimodo_isolated_runtime": preview_runtime_audit.get("kimodo_isolated_runtime")
        or {},
        "recommended_transformers_strategy": preview_runtime_audit.get(
            "recommended_transformers_strategy"
        ),
    }


async def build_talking_head_runtime_plan_payload(
    *,
    tenant_id: str,
    comfyui_url: Optional[str] = None,
) -> Dict[str, Any]:
    registered_runtime = await _resolve_registered_runtime()
    resolved_url = _resolve_comfyui_url(
        requested_url=comfyui_url,
        registered_runtime=registered_runtime,
    )
    runtime = _build_runtime_summary(resolved_url)
    plan = build_talking_head_runtime_plan(
        runtime_snapshot=runtime.get("runtime_snapshot"),
    )
    return {
        "tenant_id": tenant_id,
        "contract": {
            "schema_version": "comfyui_runtime.talking_head_runtime_plan.v1",
            "narrative_state": plan.get("narrative_state", "unknown"),
            "dispatch_source_policy": "source_record_only",
        },
        "runtime_ref": {
            **registered_runtime,
            **runtime,
        },
        "talking_head_runtime": plan,
    }


async def build_regional_adapter_runtime_plan_payload(
    *,
    tenant_id: str,
    comfyui_url: Optional[str] = None,
) -> Dict[str, Any]:
    registered_runtime = await _resolve_registered_runtime()
    resolved_url = _resolve_comfyui_url(
        requested_url=comfyui_url,
        registered_runtime=registered_runtime,
    )
    runtime = _build_runtime_summary(resolved_url)
    plan = build_regional_adapter_runtime_plan(
        runtime_snapshot=runtime.get("runtime_snapshot"),
    )
    if plan.get("readiness_state") == "ready":
        plan = _merge_regional_adapter_host_readiness(plan=plan)
    return {
        "tenant_id": tenant_id,
        "contract": {
            "schema_version": "comfyui_runtime.regional_adapter_runtime_plan.v1",
            "narrative_state": plan.get("narrative_state", "unknown"),
            "dispatch_source_policy": "source_record_only",
        },
        "runtime_ref": {
            **registered_runtime,
            **runtime,
        },
        "regional_adapter_runtime": plan,
    }
