from __future__ import annotations

import importlib.util
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

try:
    from app.services.artifact_review_decision import (
        build_followup_action_plan,
    )
    from app.services.artifact_review_followup_contract import (
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED,
        canonicalize_followup_plan_flags,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )
except ImportError:
    from backend.app.services.artifact_review_decision import (
        build_followup_action_plan,
    )
    from backend.app.services.artifact_review_followup_contract import (
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED,
        canonicalize_followup_plan_flags,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )

from capabilities.comfyui_runtime.tools.health_check import health_check
from capabilities.layer_asset_forge.services.runtime_install import build_runtime_install_plan
from capabilities.multi_media_studio.models import production_run
from capabilities.video_renderer.services.workflow_manager import WorkflowManager

_FALLBACK_COMFYUI_URLS = (
    "http://localhost:8188",
    "http://host.docker.internal:8188",
)
_WORKBENCH_SUMMARY_SCHEMA_VERSION = "comfyui_runtime.workbench.summary.v1"
_WORKBENCH_RUN_SCHEMA_VERSION = "comfyui_runtime.workbench.run.v1"
_WORKBENCH_BINDING_SCHEMA_VERSION = "comfyui_runtime.workbench.binding.v1"
_WORKBENCH_PROFILES_SCHEMA_VERSION = "comfyui_runtime.workbench.profiles.v1"
_WORKBENCH_RUNTIME_HEALTH_SCHEMA_VERSION = "comfyui_runtime.workbench.runtime_health.v1"

_ROLE_SUBFOLDER_MAP = {
    "diffusion_checkpoint": "checkpoints",
    "lora": "loras",
    "vae": "vae",
    "controlnet": "controlnet",
    "clip_vision": "clip_vision",
    "segmentation": "segmentation",
    "pose_detector": "pose_detector",
    "upscale": "upscale",
    "inpainting": "inpainting",
    "llm": "llms",
    "matting": "matting",
}

_RENDER_LANE_REQUIRED_NODES = [
    "CheckpointLoaderSimple",
    "VAELoader",
    "ControlNetLoader",
    "DualCLIPLoader",
    "OpenposePreprocessor",
]


def _manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "manifest.yaml"


def _laf_manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / "layer_asset_forge" / "model-manifest.yaml"


def _load_manifest() -> Dict[str, Any]:
    with open(_manifest_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_laf_manifest() -> Dict[str, Any]:
    with open(_laf_manifest_path(), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _model_index(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        model.get("model_id"): model
        for model in manifest.get("models", [])
        if isinstance(model, dict) and model.get("model_id")
    }


def _flatten_available_model_files(runtime_snapshot: Optional[Dict[str, Any]]) -> set[str]:
    if not runtime_snapshot:
        return set()
    available_models = runtime_snapshot.get("available_models") or {}
    discovered: set[str] = set()
    for file_list in available_models.values():
        if isinstance(file_list, list):
            for filename in file_list:
                if isinstance(filename, str) and filename.strip():
                    discovered.add(filename.strip())
    return discovered


def _flatten_available_nodes(runtime_snapshot: Optional[Dict[str, Any]]) -> set[str]:
    if not runtime_snapshot:
        return set()
    return {
        str(name).strip()
        for name in runtime_snapshot.get("available_nodes", []) or []
        if str(name).strip()
    }


def _models_storage_root() -> Path:
    explicit = os.getenv("MINDSCAPE_MODELS_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".mindscape" / "models"


def _discover_pack_model_files(pack_code: str, manifest: Dict[str, Any]) -> set[str]:
    root = _models_storage_root()
    discovered: set[str] = set()
    for model in manifest.get("models", []) or []:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("model_id") or "").strip()
        if not model_id:
            continue
        role = str(model.get("role") or "").strip()
        role_subfolder = _ROLE_SUBFOLDER_MAP.get(role, role or "other")
        candidate_dirs = [
            root / pack_code / model_id,
            root / role_subfolder / "by_pack" / pack_code / model_id,
            root / role_subfolder / model_id,
            root / role_subfolder / "store",
        ]
        for file_info in model.get("files", []) or []:
            filename = str((file_info or {}).get("filename") or "").strip()
            if not filename:
                continue
            if any((candidate_dir / filename).exists() for candidate_dir in candidate_dirs):
                discovered.add(filename)
                continue
            store_matches = list((root / role_subfolder / "store").glob(f"*/{filename}"))
            if store_matches:
                discovered.add(filename)
    return discovered


def _available_runtime_packages(package_names: List[str]) -> List[str]:
    return [
        name for name in package_names
        if isinstance(name, str) and name.strip() and importlib.util.find_spec(name.strip()) is not None
    ]


def _profile_readiness_entries(
    manifest: Dict[str, Any],
    runtime_snapshot: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    models = _model_index(manifest)
    installed_files = _flatten_available_model_files(runtime_snapshot)
    entries: List[Dict[str, Any]] = []

    for profile in manifest.get("profiles", []):
        if not isinstance(profile, dict):
            continue

        required_model_ids = [
            mid for mid in profile.get("model_ids", []) if mid in models
        ]
        required_files: List[str] = []
        for model_id in required_model_ids:
            for file_info in models[model_id].get("files", []) or []:
                filename = file_info.get("filename")
                if isinstance(filename, str) and filename:
                    required_files.append(filename)

        missing_files = [name for name in required_files if name not in installed_files]
        entries.append(
            {
                "profile_id": profile.get("profile_id"),
                "display_name": profile.get("display_name"),
                "description": profile.get("description"),
                "model_ids": required_model_ids,
                "required_files": required_files,
                "missing_files": missing_files,
                "installed_file_count": len(required_files) - len(missing_files),
                "required_file_count": len(required_files),
                "ready": len(required_files) == 0 or len(missing_files) == 0,
            }
        )

    return entries


def _lane_entry(
    *,
    lane_id: str,
    display_name: str,
    lane_scope: str,
    supported_object_classes: List[str],
    required_models: List[str],
    available_model_files: set[str],
    required_nodes: List[str],
    available_nodes: set[str],
    availability_source: str,
    required_runtime_packages: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    missing_models = [name for name in required_models if name not in available_model_files]
    available_models = [name for name in required_models if name in available_model_files]
    missing_nodes = [name for name in required_nodes if name not in available_nodes]
    available_node_list = [name for name in required_nodes if name in available_nodes]
    runtime_packages = [name for name in (required_runtime_packages or []) if isinstance(name, str) and name.strip()]
    available_runtime_packages = _available_runtime_packages(runtime_packages)
    missing_runtime_packages = [
        name for name in runtime_packages if name not in available_runtime_packages
    ]
    if required_models and missing_models:
        ready_verdict = "missing_models"
    elif required_nodes and missing_nodes:
        ready_verdict = "missing_nodes"
    elif runtime_packages and missing_runtime_packages:
        ready_verdict = "missing_runtime"
    else:
        ready_verdict = "ready"
    payload = {
        "lane_id": lane_id,
        "display_name": display_name,
        "lane_scope": lane_scope,
        "supported_object_classes": supported_object_classes,
        "required_models": required_models,
        "available_models": available_models,
        "missing_models": missing_models,
        "required_nodes": required_nodes,
        "available_nodes": available_node_list,
        "missing_nodes": missing_nodes,
        "required_runtime_packages": runtime_packages,
        "available_runtime_packages": available_runtime_packages,
        "missing_runtime_packages": missing_runtime_packages,
        "ready_verdict": ready_verdict,
        "available": ready_verdict == "ready",
        "availability_source": availability_source,
    }
    if extra:
        payload.update(extra)
    return payload


def _build_lane_entries(
    *,
    comfy_manifest: Dict[str, Any],
    laf_manifest: Dict[str, Any],
    runtime_snapshot: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    comfy_model_index = _model_index(comfy_manifest)
    laf_model_index = _model_index(laf_manifest)
    comfy_available_files = _flatten_available_model_files(runtime_snapshot)
    available_nodes = _flatten_available_nodes(runtime_snapshot)
    profile_entries = _profile_readiness_entries(
        manifest=comfy_manifest,
        runtime_snapshot=runtime_snapshot,
    )
    render_profiles = [
        profile
        for profile in profile_entries
        if profile.get("profile_id") in {"vr_preview_local", "vr_generative", "vr_wan22_14b_kj"}
    ]
    render_required_files: List[str] = []
    seen_files: set[str] = set()
    for profile in render_profiles:
        for filename in profile.get("required_files", []) or []:
            if filename in seen_files:
                continue
            seen_files.add(filename)
            render_required_files.append(filename)

    object_render_lane = _lane_entry(
        lane_id="object_render",
        display_name="Object Render Lane",
        lane_scope="object_render",
        supported_object_classes=["props", "scene_objects", "pose_guided_subjects"],
        required_models=render_required_files,
        available_model_files=comfy_available_files,
        required_nodes=_RENDER_LANE_REQUIRED_NODES,
        available_nodes=available_nodes,
        availability_source="comfyui_runtime_snapshot",
        extra={
            "profiles": render_profiles,
        },
    )
    if render_profiles:
        ready_profiles = [profile["profile_id"] for profile in render_profiles if profile.get("ready")]
        if ready_profiles and object_render_lane["ready_verdict"] != "ready":
            object_render_lane["ready_verdict"] = "partial"
            object_render_lane["available"] = False
        object_render_lane["ready_profile_ids"] = ready_profiles

    laf_runtime_plan = _build_laf_runtime_plan()
    plan_models = {
        str(item.get("model_id") or "").strip(): item
        for item in laf_runtime_plan.get("models", []) or []
        if isinstance(item, dict) and str(item.get("model_id") or "").strip()
    }

    def _laf_lane_entry(
        *,
        lane_id: str,
        display_name: str,
        lane_scope: str,
        supported_object_classes: List[str],
        model_ids: List[str],
        fallback_modes: Optional[List[str]] = None,
        automation_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        required_models: List[str] = []
        available_models: List[str] = []
        missing_models: List[str] = []
        required_runtime_packages: List[str] = []
        available_runtime_packages: List[str] = []
        missing_runtime_packages: List[str] = []
        missing_python_packages: List[str] = []
        auto_pip_specs: List[str] = []
        source_install_specs: List[str] = []
        manual_only_specs: List[str] = []

        for model_id in model_ids:
            manifest_model = laf_model_index.get(model_id) or {}
            plan_model = plan_models.get(model_id) or {}
            for file_info in manifest_model.get("files", []) or []:
                filename = str((file_info or {}).get("filename") or "").strip()
                if filename:
                    required_models.append(filename)
                    if bool(plan_model.get("model_available")):
                        available_models.append(filename)
                    else:
                        missing_models.append(filename)
            runtime_package = str(plan_model.get("runtime_package") or "").strip()
            if runtime_package:
                required_runtime_packages.append(runtime_package)
                if bool(plan_model.get("runtime_available")):
                    available_runtime_packages.append(runtime_package)
                else:
                    missing_runtime_packages.append(runtime_package)
            missing_python_packages.extend(
                [pkg for pkg in plan_model.get("missing_python_packages") or [] if isinstance(pkg, str)]
            )
            runtime_install_spec = str(plan_model.get("runtime_install_spec") or "").strip()
            runtime_install_mode = str(plan_model.get("runtime_install_mode") or "").strip()
            runtime_install_state = str(plan_model.get("runtime_install_state") or "").strip()
            if not runtime_install_spec or runtime_install_state == "ready":
                continue
            if runtime_install_mode == "source_install":
                if runtime_install_spec not in source_install_specs:
                    source_install_specs.append(runtime_install_spec)
            elif runtime_install_mode == "manual_only":
                if runtime_install_spec not in manual_only_specs:
                    manual_only_specs.append(runtime_install_spec)
            else:
                if runtime_install_spec not in auto_pip_specs:
                    auto_pip_specs.append(runtime_install_spec)

        if required_models and missing_models:
            ready_verdict = "missing_models"
        elif source_install_specs:
            ready_verdict = "source_install_required"
        elif manual_only_specs:
            ready_verdict = "manual_required"
        elif missing_runtime_packages or missing_python_packages or auto_pip_specs:
            ready_verdict = "missing_runtime"
        else:
            ready_verdict = "ready"

        payload = {
            "lane_id": lane_id,
            "display_name": display_name,
            "lane_scope": lane_scope,
            "supported_object_classes": supported_object_classes,
            "required_models": required_models,
            "available_models": available_models,
            "missing_models": missing_models,
            "required_nodes": [],
            "available_nodes": [],
            "missing_nodes": [],
            "required_runtime_packages": required_runtime_packages,
            "available_runtime_packages": available_runtime_packages,
            "missing_runtime_packages": missing_runtime_packages,
            "missing_python_packages": missing_python_packages,
            "auto_pip_packages": [
                spec
                for spec in (laf_runtime_plan.get("auto_pip_packages") or laf_runtime_plan.get("installable_python_packages") or [])
                if spec in [*missing_python_packages, *auto_pip_specs]
            ],
            "source_install_specs": source_install_specs,
            "manual_only_specs": manual_only_specs,
            "ready_verdict": ready_verdict,
            "available": ready_verdict == "ready",
            "availability_source": "layer_asset_forge.runtime_plan",
            "install_target": laf_runtime_plan.get("install_target"),
            "mutates_shared_runtime": laf_runtime_plan.get("mutates_shared_runtime"),
            "compose_baseline_required": laf_runtime_plan.get("compose_baseline_required"),
            "missing_runtime_install_specs": [
                spec
                for spec in (laf_runtime_plan.get("missing_runtime_install_specs") or [])
                if spec in [*auto_pip_specs, *source_install_specs, *manual_only_specs]
            ],
            "install_command_preview": list(laf_runtime_plan.get("install_command_preview") or []),
            "runtime_plan_ref": {
                "pack_code": "layer_asset_forge",
                "endpoint": "/api/v1/capabilities/layer_asset_forge/runtime/plan",
            },
        }
        if fallback_modes:
            payload["fallback_modes"] = fallback_modes
        if automation_level:
            payload["automation_level"] = automation_level
        return payload

    selection_lane = _laf_lane_entry(
        lane_id="object_selection_mask_proposal",
        display_name="Object Selection / Mask Proposal Lane",
        lane_scope="selection_mask_proposal",
        supported_object_classes=["general_objects", "props", "background_elements"],
        model_ids=["sam2_hiera_large"],
        fallback_modes=["provided_mask_ref", "bbox_hint_rect_mask"],
        automation_level=(
            "automatic"
            if not plan_models.get("sam2_hiera_large", {}).get("missing_python_packages")
            and bool(plan_models.get("sam2_hiera_large", {}).get("runtime_available"))
            else "manual_or_bbox_fallback"
        ),
    )

    portrait_lane = _laf_lane_entry(
        lane_id="portrait_matte",
        display_name="Portrait Matte Lane",
        lane_scope="portrait_matte_refinement",
        supported_object_classes=["portrait_human", "hair", "upper_body"],
        model_ids=["modnet_photographic"],
    )

    completion_lane = _laf_lane_entry(
        lane_id="background_completion",
        display_name="Background Completion Lane",
        lane_scope="completion_hole_filling",
        supported_object_classes=["background_holes", "plate_cleanup"],
        model_ids=["lama_big"],
    )

    return [
        selection_lane,
        portrait_lane,
        completion_lane,
        object_render_lane,
    ]


def _recommended_state(*, lane: Dict[str, Any]) -> str:
    verdict = str(lane.get("ready_verdict") or "").strip()
    if verdict == "ready":
        return "ready"
    if verdict == "partial":
        return "degraded"
    fallback_modes = [
        mode
        for mode in (lane.get("fallback_modes") or [])
        if isinstance(mode, str) and mode.strip()
    ]
    automation_level = str(lane.get("automation_level") or "").strip()
    if fallback_modes or automation_level == "manual_or_bbox_fallback":
        return "degraded"
    return "blocked"


def _build_laf_runtime_plan() -> Dict[str, Any]:
    try:
        return build_runtime_install_plan()
    except Exception as exc:
        return {
            "pack_code": "layer_asset_forge",
            "install_target": "host_optional_runtime",
            "isolation_mode": "host_managed_runtime",
            "narrative_state": "installer_unavailable",
            "compose_baseline_required": False,
            "mutates_shared_runtime": False,
            "isolated_runtime_supported": True,
            "selection_source": "default_runtime_models",
            "selected_profile_id": None,
            "selected_model_ids": [],
            "readiness_state": "unknown",
            "device_node_available": False,
            "host_bridge_state": "unavailable",
            "models": [],
            "required_python_packages": [],
            "missing_python_packages": [],
            "required_runtime_install_specs": [],
            "missing_runtime_install_specs": [],
            "auto_pip_runtime_specs": [],
            "source_install_specs": [],
            "manual_only_specs": [],
            "auto_pip_packages": [],
            "installable_python_packages": [],
            "install_command_preview": [],
            "error": str(exc),
        }


def _failure_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "code": "mask_missing",
            "scope": "object_extract",
            "requires_binding_context": True,
        },
        {
            "code": "matte_lane_not_applicable",
            "scope": "portrait_matte",
            "requires_binding_context": True,
        },
        {
            "code": "renderer_slot_incompatible",
            "scope": "object_render",
            "requires_binding_context": False,
        },
        {
            "code": "missing_scene_context",
            "scope": "binding",
            "requires_binding_context": True,
        },
        {
            "code": "snapshot_binding_stale",
            "scope": "binding",
            "requires_binding_context": True,
        },
    ]


async def _resolve_registered_runtime() -> Dict[str, Any]:
    local_core_base = os.getenv("LOCAL_CORE_API_BASE", "http://localhost:8200")
    api_key = os.getenv("LOCAL_CORE_API_KEY", "")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{local_core_base}/api/v1/runtime-environments",
                headers=headers,
            )
            resp.raise_for_status()
            payload = resp.json()
            runtimes = payload.get("runtimes", []) if isinstance(payload, dict) else []
            for runtime in runtimes:
                if runtime.get("name") == "ComfyUI Local":
                    return {
                        "registration_state": "registered",
                        "runtime_id": runtime.get("id"),
                        "name": runtime.get("name"),
                        "config_url": runtime.get("config_url"),
                        "status": runtime.get("status"),
                    }
    except Exception as exc:
        return {
            "registration_state": "unknown",
            "runtime_id": None,
            "name": "ComfyUI Local",
            "config_url": None,
            "status": None,
            "error": str(exc),
        }

    return {
        "registration_state": "not_registered",
        "runtime_id": None,
        "name": "ComfyUI Local",
        "config_url": None,
        "status": None,
    }


def _resolve_comfyui_url(
    *,
    requested_url: Optional[str],
    registered_runtime: Dict[str, Any],
) -> str:
    return (
        (requested_url or "").strip()
        or str(registered_runtime.get("config_url") or "").strip()
        or os.getenv("COMFYUI_RUNTIME_URL", "").strip()
        or os.getenv("COMFYUI_URL", "").strip()
        or _FALLBACK_COMFYUI_URLS[0]
    )


def _build_runtime_summary(comfyui_url: str) -> Dict[str, Any]:
    candidate_urls: List[str] = []
    for candidate in [comfyui_url, *_FALLBACK_COMFYUI_URLS]:
        normalized = str(candidate or "").strip()
        if normalized and normalized not in candidate_urls:
            candidate_urls.append(normalized)

    last_error: Optional[str] = None
    health: Optional[Dict[str, Any]] = None
    selected_url = comfyui_url
    for candidate in candidate_urls:
        try:
            health = health_check(comfyui_url=candidate)
            selected_url = candidate
            break
        except Exception as exc:
            last_error = str(exc)

    if health is None:
        return {
            "live_status": "error",
            "comfyui_url": comfyui_url,
            "error": last_error or "runtime_unavailable",
            "runtime_snapshot": None,
        }

    snapshot = WorkflowManager(workspace_root="/tmp").create_runtime_snapshot(
        runtime_id="comfyui_local",
        health_data=health,
    )
    return {
        "live_status": "ok",
        "comfyui_url": health.get("comfyui_url", selected_url),
        "gpu": health.get("gpu"),
        "os": health.get("os"),
        "python_version": health.get("python_version"),
        "node_count": health.get("node_count"),
        "runtime_snapshot": asdict(snapshot),
    }


def _default_source_ref(kind: str, identifier: Optional[str]) -> Optional[Dict[str, str]]:
    value = str(identifier or "").strip()
    if not value:
        return None
    return {"kind": kind, "id": value}


def _resolve_run_compat_state(run: Dict[str, Any]) -> str:
    explicit = str(run.get("compat_state") or "").strip()
    if explicit:
        return explicit
    snapshot = run.get("workload_snapshot") or {}
    if isinstance(snapshot, dict) and snapshot.get("usage_scene_ids") and not snapshot.get("usage_bindings"):
        return "legacy_projection"
    return "native_source"


def _review_bundle_ref(provider_metadata: Dict[str, Any]) -> Dict[str, Any]:
    refs = provider_metadata.get("review_bundle_refs")
    if not isinstance(refs, list):
        return {}
    for item in refs:
        if isinstance(item, dict):
            return dict(item)
    return {}


def _canonicalize_followup_plan(followup_plan: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(followup_plan, dict):
        return {}
    lanes = []
    for item in (followup_plan.get("lanes") or []):
        if not isinstance(item, dict):
            continue
        lanes.append(
            {
                **dict(item),
                "lane_id": normalize_followup_lane_id(item.get("lane_id")) or None,
                "consumer_kind": normalize_followup_consumer_kind(item.get("consumer_kind"))
                or None,
                "action_ids": [
                    normalize_followup_action_id(action_id)
                    for action_id in (item.get("action_ids") or [])
                    if normalize_followup_action_id(action_id)
                ],
            }
        )

    return canonicalize_followup_plan_flags({
        **dict(followup_plan),
        "action_ids": [
            normalize_followup_action_id(action_id)
            for action_id in (followup_plan.get("action_ids") or [])
            if normalize_followup_action_id(action_id)
        ],
        "lane_ids": [
            normalize_followup_lane_id(lane_id)
            for lane_id in (followup_plan.get("lane_ids") or [])
            if normalize_followup_lane_id(lane_id)
        ],
        "lanes": lanes,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED: bool(
            followup_plan.get(FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED)
            or followup_plan.get("publish_candidate_requested")
        ),
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY: bool(
            followup_plan.get(FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY)
            or followup_plan.get("publish_candidate_ready")
        ),
    })


def _canonicalize_followup_request_refs(refs: Any) -> List[Dict[str, Any]]:
    return [
        {
            **dict(item),
            "lane_id": normalize_followup_lane_id(item.get("lane_id")) or None,
            "consumer_kind": normalize_followup_consumer_kind(item.get("consumer_kind"))
            or None,
        }
        for item in (refs or [])
        if isinstance(item, dict)
    ]


def _scene_review_followup(run: Dict[str, Any], scene_result: Dict[str, Any]) -> Dict[str, Any]:
    provider_metadata = (
        dict(scene_result.get("provider_metadata") or {})
        if isinstance(scene_result.get("provider_metadata"), dict)
        else {}
    )
    review_decision_ref = (
        dict(provider_metadata.get("review_decision_ref") or {})
        if isinstance(provider_metadata.get("review_decision_ref"), dict)
        else {}
    )
    bundle_ref = _review_bundle_ref(provider_metadata)
    followup_plan = (
        dict(provider_metadata.get("downstream_action_plan") or {})
        if isinstance(provider_metadata.get("downstream_action_plan"), dict)
        else {}
    )
    if not followup_plan and isinstance(review_decision_ref.get("downstream_action_plan"), dict):
        followup_plan = dict(review_decision_ref.get("downstream_action_plan") or {})
    if not followup_plan:
        followup_plan = build_followup_action_plan(
            review_bundle_id=str(
                review_decision_ref.get("artifact_id")
                or bundle_ref.get("review_bundle_id")
                or ""
            ),
            decision=str(
                review_decision_ref.get("decision")
                or provider_metadata.get("visual_acceptance_state")
                or ""
            ),
            run_id=str(run.get("run_id") or ""),
            scene_id=str(scene_result.get("scene_id") or ""),
            source_kind=str(bundle_ref.get("source_kind") or ""),
            package_id=str(provider_metadata.get("package_id") or bundle_ref.get("package_id") or ""),
            preset_id=str(provider_metadata.get("preset_id") or bundle_ref.get("preset_id") or ""),
            artifact_ids=provider_metadata.get("artifact_ids") or bundle_ref.get("artifact_ids") or [],
            binding_mode=str(
                provider_metadata.get("binding_mode") or bundle_ref.get("binding_mode") or ""
            ),
            followup_actions=review_decision_ref.get("followup_actions"),
        )
    else:
        followup_plan = _canonicalize_followup_plan(followup_plan)

    action_ids = [
        str(item or "").strip()
        for item in (followup_plan.get("action_ids") or [])
        if str(item or "").strip()
    ]
    if not action_ids:
        return {}

    lane_ids = [
        str(item or "").strip()
        for item in (followup_plan.get("lane_ids") or [])
        if str(item or "").strip()
    ]
    lanes = [
        dict(item)
        for item in (followup_plan.get("lanes") or [])
        if isinstance(item, dict)
    ]
    return {
        "scene_id": str(scene_result.get("scene_id") or "").strip() or None,
        "status": str(scene_result.get("status") or "").strip() or None,
        "renderer": str(scene_result.get("renderer") or "").strip() or None,
        "visual_acceptance_state": str(
            provider_metadata.get("visual_acceptance_state") or review_decision_ref.get("decision") or ""
        ).strip()
        or None,
        "reviewed_at": str(review_decision_ref.get("reviewed_at") or "").strip() or None,
        "artifact_id": str(review_decision_ref.get("artifact_id") or "").strip() or None,
        "review_bundle_id": str(
            followup_plan.get("review_bundle_id") or bundle_ref.get("review_bundle_id") or ""
        ).strip()
        or None,
        "action_ids": action_ids,
        "lane_ids": lane_ids,
        "lanes": lanes,
        "dispatchable_lane_count": int(followup_plan.get("dispatchable_lane_count") or 0),
        "blocked_lane_count": int(followup_plan.get("blocked_lane_count") or 0),
        "rerender_required": bool(followup_plan.get("rerender_required")),
        "manual_escalation_required": bool(
            followup_plan.get("manual_escalation_required")
        ),
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED: bool(
            followup_plan.get(FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED)
        ),
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY: bool(
            followup_plan.get(FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY)
        ),
        "followup_request_refs": _canonicalize_followup_request_refs(
            provider_metadata.get("followup_request_refs")
        ),
    }


def _aggregate_review_followups(run: Dict[str, Any]) -> Dict[str, Any]:
    summary = {
        "scenes_with_followups": 0,
        "action_counts": {},
        "lane_counts": {},
        "dispatchable_lane_counts": {},
        "blocked_lane_counts": {},
        "followup_request_state_counts": {},
        "capability_consumer_handoff_ready_scene_ids": [],
        "manual_escalation_scene_ids": [],
        "rerender_scene_ids": [],
        "scene_refs": [],
    }
    for scene_result in run.get("scene_results", []) or []:
        if not isinstance(scene_result, dict):
            continue
        scene_followup = _scene_review_followup(run, scene_result)
        if not scene_followup:
            continue
        summary["scenes_with_followups"] += 1
        summary["scene_refs"].append(scene_followup)
        scene_id = str(scene_followup.get("scene_id") or "").strip()
        for action_id in scene_followup.get("action_ids") or []:
            summary["action_counts"][action_id] = summary["action_counts"].get(action_id, 0) + 1
        for lane in scene_followup.get("lanes") or []:
            if not isinstance(lane, dict):
                continue
            lane_id = str(lane.get("lane_id") or "").strip()
            if not lane_id:
                continue
            summary["lane_counts"][lane_id] = summary["lane_counts"].get(lane_id, 0) + 1
            dispatch_state = str(lane.get("dispatch_state") or "").strip()
            if dispatch_state == "ready":
                summary["dispatchable_lane_counts"][lane_id] = (
                    summary["dispatchable_lane_counts"].get(lane_id, 0) + 1
                )
            elif dispatch_state == "blocked":
                summary["blocked_lane_counts"][lane_id] = (
                    summary["blocked_lane_counts"].get(lane_id, 0) + 1
                )
        if scene_followup.get(FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY) and scene_id:
            summary["capability_consumer_handoff_ready_scene_ids"].append(scene_id)
        for request_ref in scene_followup.get("followup_request_refs") or []:
            if not isinstance(request_ref, dict):
                continue
            request_state = str(request_ref.get("request_state") or "").strip()
            if not request_state:
                continue
            summary["followup_request_state_counts"][request_state] = (
                summary["followup_request_state_counts"].get(request_state, 0) + 1
            )
        if scene_followup.get("manual_escalation_required") and scene_id:
            summary["manual_escalation_scene_ids"].append(scene_id)
        if scene_followup.get("rerender_required") and scene_id:
            summary["rerender_scene_ids"].append(scene_id)
    return summary


def _summarize_run(run: Dict[str, Any]) -> Dict[str, Any]:
    scene_results = run.get("scene_results", []) or []
    counts = {
        "total": len(scene_results),
        "completed": 0,
        "failed": 0,
        "blocked": 0,
        "skipped": 0,
        "awaiting_upload": 0,
        "other": 0,
    }
    for scene in scene_results:
        status = str(scene.get("status") or "").strip()
        if status in counts and status != "total":
            counts[status] += 1
        elif status:
            counts["other"] += 1

    run_id = run.get("run_id")
    default_source_ref = _default_source_ref("production_run", run_id)
    source_workload_ref = run.get("source_workload_ref") or default_source_ref
    source_run_ref = run.get("source_run_ref") or default_source_ref
    source_projection_ref = run.get("source_projection_ref")
    record_role = str(run.get("record_role") or "source_record").strip() or "source_record"
    is_derived_projection = bool(run.get("is_derived_projection")) or record_role == "derived_projection"
    workload_snapshot = run.get("workload_snapshot") or {}
    review_followups = _aggregate_review_followups(run)
    return {
        "run_id": run.get("run_id"),
        "project_id": run.get("project_id"),
        "storyboard_id": run.get("storyboard_id"),
        "status": run.get("status"),
        "source_type": run.get("source_type"),
        "direction_ir_id": run.get("direction_ir_id"),
        "render_profile": run.get("render_profile") or {},
        "workload_snapshot": workload_snapshot,
        "object_contract_summary": (
            dict(workload_snapshot.get("object_contract_summary") or {})
            if isinstance(workload_snapshot, dict)
            else {}
        ),
        "compatibility_matrix": (
            dict(workload_snapshot.get("compatibility_matrix") or {})
            if isinstance(workload_snapshot, dict)
            else {}
        ),
        "review_followups": review_followups,
        "scene_counts": counts,
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "schema_version": str(run.get("schema_version") or _WORKBENCH_RUN_SCHEMA_VERSION),
        "compat_state": _resolve_run_compat_state(run),
        "record_role": record_role,
        "is_derived_projection": is_derived_projection,
        "source_workload_ref": source_workload_ref,
        "source_run_ref": source_run_ref,
        "source_projection_ref": source_projection_ref,
        "dispatch_source_allowed": (
            bool(run.get("dispatch_source_allowed"))
            if "dispatch_source_allowed" in run
            else record_role == "source_record"
        ),
    }


def _summarize_scene_projection(run: Dict[str, Any], scene_result: Dict[str, Any]) -> Dict[str, Any]:
    base_summary = _summarize_run(run)
    scene_id = str(scene_result.get("scene_id") or "").strip()
    projection_ref = _default_source_ref("scene_result", scene_id)
    compat_state = "projection_ready" if projection_ref else "projection_incomplete"
    projection_id = f"{base_summary['run_id']}:{scene_id}" if scene_id else f"{base_summary['run_id']}:scene"
    review_followup = _scene_review_followup(run, scene_result)
    return {
        **base_summary,
        "projection_id": projection_id,
        "workload_kind": "scene_projection",
        "record_role": "derived_projection",
        "is_derived_projection": True,
        "dispatch_source_allowed": False,
        "compat_state": compat_state,
        "status": scene_result.get("status") or base_summary.get("status"),
        "scene_id": scene_id,
        "scene_renderer": scene_result.get("renderer"),
        "prompt_id": scene_result.get("prompt_id"),
        "vr_commit_id": scene_result.get("vr_commit_id"),
        "timeline_item_ids": scene_result.get("timeline_item_ids") or [],
        "review_followup": review_followup,
        "source_workload_ref": base_summary.get("source_workload_ref"),
        "source_run_ref": base_summary.get("source_run_ref"),
        "source_projection_ref": projection_ref,
    }


def _scene_binding_projections(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    snapshot = run.get("workload_snapshot") or {}
    projections = snapshot.get("scene_binding_projections") if isinstance(snapshot, dict) else []
    items: List[Dict[str, Any]] = []
    for projection in projections or []:
        if not isinstance(projection, dict):
            continue
        items.append(dict(projection))
    return items


def get_workbench_binding(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    scene_id: Optional[str] = None,
) -> Dict[str, Any]:
    run = production_run.get_run(tenant_id, project_id, run_id)
    if not run:
        raise KeyError(f"run_not_found: {run_id}")

    summary = _summarize_run(run)
    all_bindings = _scene_binding_projections(run)
    selected_scene_id = str(scene_id or "").strip()
    filtered_bindings = [
        item
        for item in all_bindings
        if not selected_scene_id or str(item.get("scene_id") or "").strip() == selected_scene_id
    ]
    binding_state = "ready" if filtered_bindings else "contract_pending"

    return {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "contract": {
            "schema_version": _WORKBENCH_BINDING_SCHEMA_VERSION,
            "narrative_state": "inspection_ready",
            "dispatch_source_policy": "source_record_only",
        },
        "record": {
            "run_id": summary.get("run_id"),
            "storyboard_id": summary.get("storyboard_id"),
            "schema_version": summary.get("schema_version"),
            "compat_state": summary.get("compat_state"),
            "record_role": summary.get("record_role"),
            "is_derived_projection": summary.get("is_derived_projection"),
            "dispatch_source_allowed": summary.get("dispatch_source_allowed"),
            "source_workload_ref": summary.get("source_workload_ref"),
            "source_run_ref": summary.get("source_run_ref"),
            "source_projection_ref": summary.get("source_projection_ref"),
            "object_contract_summary": summary.get("object_contract_summary") or {},
            "compatibility_matrix": summary.get("compatibility_matrix") or {},
        },
        "binding_inspector_state": binding_state,
        "count": len(filtered_bindings),
        "bindings": filtered_bindings,
    }


def list_workbench_runs(
    *,
    tenant_id: str,
    project_id: str,
    limit: int = 10,
    include_scene_projections: bool = False,
) -> List[Dict[str, Any]]:
    runs = production_run.list_runs(tenant_id, project_id)
    items: List[Dict[str, Any]] = []
    for run in runs:
        items.append(_summarize_run(run))
        if include_scene_projections:
            for scene_result in run.get("scene_results", []) or []:
                if isinstance(scene_result, dict):
                    items.append(_summarize_scene_projection(run, scene_result))
    return items[: max(limit, 0)]


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
            "auto_pip_packages": list(laf_runtime_plan.get("auto_pip_packages") or laf_runtime_plan.get("installable_python_packages") or []),
            "installable_python_packages": list(laf_runtime_plan.get("installable_python_packages") or []),
            "missing_runtime_install_specs": list(laf_runtime_plan.get("missing_runtime_install_specs") or []),
            "missing_model_weight_ids": list(laf_runtime_plan.get("missing_model_weight_ids") or []),
            "install_command_preview": list(laf_runtime_plan.get("install_command_preview") or []),
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
    }

    active_failures: List[str] = []
    if str(object_selection_lane.get("ready_verdict") or "").strip() != "ready":
        active_failures.append("mask_missing")
    if str(object_render_lane.get("ready_verdict") or "").strip() in {"missing_nodes", "missing_models"}:
        active_failures.append("renderer_slot_incompatible")

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
        "runtime_ref": runtime_ref,
        "laf_runtime": laf_runtime,
    }
