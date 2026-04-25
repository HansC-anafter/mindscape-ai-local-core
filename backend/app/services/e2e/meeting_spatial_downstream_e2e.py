from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import text

from backend.app.models.handoff import HandoffIn
from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import ConversationThread
from backend.app.services.conversation.pipeline_core import PipelineCore
from backend.app.services.governance.governance_context_read_model import (
    GovernanceContextReadModel,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.spatial_scheduling_compiler import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    build_spatial_schedule_artifact,
    build_spatial_schedule_context,
    build_spatial_scheduling_ir,
    normalize_spatial_schedule_context,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)
from backend.app.services.visual_acceptance_bundle import (
    build_visual_acceptance_bundle,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
LOCAL_CORE_REPO = WORKSPACE_ROOT / "mindscape-ai-local-core"
CLOUD_REPO = WORKSPACE_ROOT / "mindscape-ai-cloud"
_SCENARIO_CONFIG_RE = re.compile(
    r"```e2e_config\s*(?P<json>\{.*?\})\s*```", re.DOTALL
)
_PATH_TOKEN_MAP = {
    "${WORKSPACE_ROOT}": WORKSPACE_ROOT,
    "${LOCAL_CORE_REPO}": LOCAL_CORE_REPO,
    "${CLOUD_REPO}": CLOUD_REPO,
}
_MOTION_ASSET_LIST_KEYS = (
    "motion_assets",
    "animation_assets",
    "actor_motion_assets",
    "camera_motion_assets",
    "pose_tracks",
    "animation_clips",
)
_MOTION_REF_KEYS = (
    "motion_asset_ref",
    "animation_ref",
    "animation_clip_ref",
    "pose_track_ref",
    "camera_motion_ref",
    "clip_ref",
    "asset_ref",
)
_KEYFRAME_LIST_KEYS = ("keyframe_evidence", "keyframes", "keyframe_evidence_refs")
_KEYFRAME_REF_KEYS = ("still_ref", "image_ref", "frame_ref", "keyframe_ref", "ref")
_FRAME_MAP_KEYS = ("frame_beat_map", "beat_frame_map")


@dataclass
class ScenarioDefinition:
    config: Dict[str, Any]
    message: str

    @property
    def scenario_id(self) -> str:
        value = str(self.config.get("scenario_id") or "").strip()
        return value or f"meeting_spatial_{uuid.uuid4().hex[:8]}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {value!r}")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _jsonable(value.dict())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _must(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _first_id(store: MindscapeStore, table: str, workspace_id: Optional[str] = None) -> Optional[str]:
    with store.get_connection() as conn:
        if workspace_id:
            row = conn.execute(
                text(
                    f"SELECT id FROM {table} WHERE workspace_id = :workspace_id "
                    "ORDER BY created_at DESC NULLS LAST LIMIT 1"
                ),
                {"workspace_id": workspace_id},
            ).fetchone()
        else:
            row = conn.execute(
                text(f"SELECT id FROM {table} ORDER BY created_at DESC NULLS LAST LIMIT 1")
            ).fetchone()
    if not row:
        return None
    return str(row[0] if not hasattr(row, "_mapping") else row._mapping["id"])


def _resolve_str_config(
    scenario: ScenarioDefinition,
    key: str,
    explicit_value: Optional[str],
) -> Optional[str]:
    if explicit_value and explicit_value.strip():
        return explicit_value.strip()
    raw = scenario.config.get(key)
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _resolve_bool_config(
    scenario: ScenarioDefinition,
    key: str,
    explicit_value: Optional[bool] = None,
    *,
    default: bool = False,
) -> bool:
    if explicit_value is not None:
        return bool(explicit_value)
    raw = scenario.config.get(key)
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_reference_payload(value: Any) -> Dict[str, Any]:
    payload = _jsonable(value)
    if isinstance(payload, str):
        normalized = payload.strip()
        return {"path": normalized} if normalized else {}
    if not isinstance(payload, dict):
        return {}
    direct_keys = (
        "storage_key",
        "url",
        "local_path",
        "identifier",
        "uri",
        "format",
        "storage_type",
        "content_type",
        "path",
    )
    direct_ref = {key: payload.get(key) for key in direct_keys if payload.get(key)}
    if direct_ref:
        return direct_ref
    for key in (
        "ref",
        "asset_ref",
        "motion_asset_ref",
        "animation_ref",
        "animation_clip_ref",
        "pose_track_ref",
        "camera_motion_ref",
        "clip_ref",
        "still_ref",
        "image_ref",
        "frame_ref",
        "keyframe_ref",
        "preview_ref",
    ):
        nested = _normalize_reference_payload(payload.get(key))
        if nested:
            return nested
    return {}


def _collect_required_motion_targets(
    execution_artifacts: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _append(target_kind: str, target_id: Any, segment_id: Any = None) -> None:
        normalized_id = str(target_id or "").strip()
        if not normalized_id:
            return
        key = (target_kind, normalized_id)
        if key in seen:
            return
        seen.add(key)
        payload: Dict[str, Any] = {
            "target_kind": target_kind,
            "target_id": normalized_id,
        }
        normalized_segment = str(segment_id or "").strip()
        if normalized_segment:
            payload["segment_id"] = normalized_segment
        targets.append(payload)

    blocking_plan = dict(execution_artifacts.get("blocking_plan_excerpt") or {})
    performance_beats = dict(execution_artifacts.get("performance_beats_excerpt") or {})
    for item in list(blocking_plan.get("blocking_paths") or []):
        if isinstance(item, dict):
            _append("blocking_path", item.get("path_id"), item.get("segment_id"))
    for item in list(performance_beats.get("performance_beats") or []):
        if isinstance(item, dict):
            _append("beat", item.get("beat_id"), item.get("segment_id"))
    for item in list(performance_beats.get("interaction_beats") or []):
        if isinstance(item, dict):
            _append("beat", item.get("beat_id"), item.get("segment_id"))
    return targets


def _normalize_motion_asset_entry(item: Any, *, source_key: str) -> Optional[Dict[str, Any]]:
    payload = _jsonable(item)
    if not isinstance(payload, dict):
        return None
    asset_ref: Dict[str, Any] = {}
    for ref_key in _MOTION_REF_KEYS:
        asset_ref = _normalize_reference_payload(payload.get(ref_key))
        if asset_ref:
            break
    if not asset_ref:
        asset_ref = _normalize_reference_payload(payload)
    if not asset_ref:
        return None
    return {
        "source_key": source_key,
        "target_id": str(
            payload.get("target_id")
            or payload.get("actor_id")
            or payload.get("object_id")
            or payload.get("entity_id")
            or payload.get("camera_id")
            or ""
        ).strip(),
        "segment_id": str(payload.get("segment_id") or "").strip(),
        "asset_ref": asset_ref,
        "metadata": dict(payload.get("metadata") or {}),
    }


def _collect_motion_asset_entries(scene_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for key in _MOTION_ASSET_LIST_KEYS:
        for item in list(scene_manifest.get(key) or []):
            entry = _normalize_motion_asset_entry(item, source_key=key)
            if entry:
                entries.append(entry)
    for item in list(scene_manifest.get("actors") or []):
        entry = _normalize_motion_asset_entry(item, source_key="actors")
        if entry:
            entries.append(entry)
    return entries


def _normalize_motion_target(
    payload: Dict[str, Any],
    *,
    default_kind: str,
) -> Optional[Dict[str, Any]]:
    normalized = _jsonable(payload)
    if not isinstance(normalized, dict):
        return None
    target_kind = str(normalized.get("target_kind") or "").strip()
    target_id = str(normalized.get("target_id") or "").strip()
    if not target_id:
        if normalized.get("beat_id"):
            target_kind = target_kind or (
                "beat"
                if default_kind in {"performance_beat", "interaction_beat"}
                else default_kind
            )
            target_id = str(normalized.get("beat_id") or "").strip()
        elif normalized.get("path_id"):
            target_kind = target_kind or "blocking_path"
            target_id = str(normalized.get("path_id") or "").strip()
    target_kind = target_kind or default_kind
    if not target_id:
        return None
    return {
        "target_kind": target_kind,
        "target_id": target_id,
        "segment_id": str(normalized.get("segment_id") or "").strip(),
    }


def _normalize_keyframe_evidence_entry(item: Any) -> Optional[Dict[str, Any]]:
    payload = _jsonable(item)
    if not isinstance(payload, dict):
        return None
    ref_payload: Dict[str, Any] = {}
    for ref_key in _KEYFRAME_REF_KEYS:
        ref_payload = _normalize_reference_payload(payload.get(ref_key))
        if ref_payload:
            break
    if not ref_payload:
        return None
    target = _normalize_motion_target(payload, default_kind="performance_beat")
    if not target:
        return None
    return {
        **target,
        "frame_index": payload.get("frame_index"),
        "timecode": payload.get("timecode"),
        "evidence_ref": ref_payload,
        "metadata": dict(payload.get("metadata") or {}),
    }


def _collect_keyframe_evidence_entries(scene_manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for key in _KEYFRAME_LIST_KEYS:
        for item in list(scene_manifest.get(key) or []):
            entry = _normalize_keyframe_evidence_entry(item)
            if entry:
                entries.append(entry)
    return entries


def _collect_clip_refs_from_downstream_result(
    downstream_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    proof_result = dict(downstream_result.get("proof_result") or {})
    clip_refs = list(proof_result.get("clip_refs") or [])
    if not clip_refs:
        clip_refs = list((proof_result.get("proof_bundle") or {}).get("clip_refs") or [])
    normalized: List[Dict[str, Any]] = []
    for ref in clip_refs:
        payload = _normalize_reference_payload(ref)
        if payload:
            normalized.append(payload)
    return normalized


def _collect_frame_beat_mappings(
    scene_manifest: Dict[str, Any],
    keyframe_entries: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    mappings: List[Dict[str, Any]] = []
    for key in _FRAME_MAP_KEYS:
        for item in list(scene_manifest.get(key) or []):
            payload = _jsonable(item)
            if not isinstance(payload, dict):
                continue
            target = _normalize_motion_target(payload, default_kind="performance_beat")
            if not target:
                continue
            mappings.append(
                {
                    **target,
                    "frame_index": payload.get("frame_index"),
                    "timecode": payload.get("timecode"),
                    "clip_index": payload.get("clip_index"),
                    "evidence_ref": _normalize_reference_payload(
                        payload.get("evidence_ref") or payload.get("ref")
                    ),
                }
            )
    if mappings:
        return mappings
    for entry in keyframe_entries:
        mappings.append(
            {
                "target_kind": entry.get("target_kind"),
                "target_id": entry.get("target_id"),
                "segment_id": entry.get("segment_id"),
                "frame_index": entry.get("frame_index"),
                "timecode": entry.get("timecode"),
                "clip_index": None,
                "evidence_ref": dict(entry.get("evidence_ref") or {}),
            }
        )
    return mappings


def _missing_required_targets(
    required_targets: Sequence[Dict[str, Any]],
    present_targets: Iterable[tuple[str, str]],
) -> List[Dict[str, Any]]:
    present = set(present_targets)
    return [
        dict(target)
        for target in required_targets
        if (str(target.get("target_kind") or ""), str(target.get("target_id") or ""))
        not in present
    ]


def build_motion_evidence_artifacts(
    *,
    scenario: ScenarioDefinition,
    downstream_input_manifest: Dict[str, Any],
    execution_artifacts: Dict[str, Dict[str, Any]],
    downstream_result: Dict[str, Any],
    emit_visual_acceptance_bundle: bool = False,
) -> Dict[str, Dict[str, Any]]:
    scene_manifest = dict(downstream_input_manifest.get("scene_manifest") or {})
    required_targets = _collect_required_motion_targets(execution_artifacts)
    motion_asset_entries = _collect_motion_asset_entries(scene_manifest)
    clip_refs = _collect_clip_refs_from_downstream_result(downstream_result)
    keyframe_entries = _collect_keyframe_evidence_entries(scene_manifest)
    frame_beat_mappings = _collect_frame_beat_mappings(scene_manifest, keyframe_entries)

    keyframe_targets = {
        (str(entry.get("target_kind") or ""), str(entry.get("target_id") or ""))
        for entry in keyframe_entries
    }
    frame_map_targets = {
        (str(entry.get("target_kind") or ""), str(entry.get("target_id") or ""))
        for entry in frame_beat_mappings
    }
    missing_keyframe_targets = _missing_required_targets(required_targets, keyframe_targets)
    missing_frame_targets = _missing_required_targets(required_targets, frame_map_targets)

    motion_asset_manifest: Dict[str, Any] = {
        "status": "materialized" if motion_asset_entries else "missing",
        "scenario_id": scenario.scenario_id,
        "required_targets": required_targets,
        "motion_asset_refs": motion_asset_entries,
        "generated_at": _now_utc(),
    }
    render_clip_manifest: Dict[str, Any] = {
        "status": "materialized" if clip_refs else "missing",
        "scenario_id": scenario.scenario_id,
        "clip_refs": clip_refs,
        "clip_count": len(clip_refs),
        "renderer": "video_renderer",
        "generated_at": _now_utc(),
    }
    keyframe_evidence_manifest: Dict[str, Any] = {
        "status": (
            "materialized"
            if keyframe_entries and not missing_keyframe_targets
            else "missing"
        ),
        "scenario_id": scenario.scenario_id,
        "required_targets": required_targets,
        "keyframe_evidence": keyframe_entries,
        "missing_required_targets": missing_keyframe_targets,
        "generated_at": _now_utc(),
    }
    frame_beat_map: Dict[str, Any] = {
        "status": (
            "materialized"
            if frame_beat_mappings and not missing_frame_targets
            else "missing"
        ),
        "scenario_id": scenario.scenario_id,
        "required_targets": required_targets,
        "mappings": frame_beat_mappings,
        "missing_required_targets": missing_frame_targets,
        "generated_at": _now_utc(),
    }

    visual_acceptance_bundle_excerpt: Dict[str, Any] = {
        "status": "not_requested",
        "scenario_id": scenario.scenario_id,
        "required_targets": required_targets,
        "render_slots": [],
        "keyframe_evidence": keyframe_entries,
        "generated_at": _now_utc(),
    }
    visual_acceptance_review_receipt: Dict[str, Any] = {
        "status": "not_requested",
        "scenario_id": scenario.scenario_id,
        "required_targets": required_targets,
        "generated_at": _now_utc(),
    }
    should_emit_visual_acceptance = emit_visual_acceptance_bundle or bool(clip_refs)
    if should_emit_visual_acceptance:
        review_scene = {
            "scene_id": str(downstream_input_manifest.get("scene_id") or scenario.scenario_id),
            "object_assets": [
                {
                    "object_target_id": asset.get("object_target_id"),
                    "asset_ref": dict(
                        asset.get("asset_ref")
                        or asset.get("object_model_ref")
                        or asset.get("object_mesh_ref")
                        or {}
                    ),
                    "metadata": dict(asset.get("metadata") or {}),
                }
                for asset in list(scene_manifest.get("object_assets") or [])
                if isinstance(asset, dict)
            ],
            "scene_manifest": scene_manifest,
            "object_workload_snapshot": {
                "required_targets": required_targets,
                "motion_asset_refs": motion_asset_entries,
                "keyframe_evidence": keyframe_entries,
            },
        }
        bundle = build_visual_acceptance_bundle(
            tenant_id=str(downstream_input_manifest.get("tenant_id") or "tenant_object_mesh_template"),
            project_id=str(
                downstream_input_manifest.get("scene_id")
                or downstream_input_manifest.get("workspace_id")
                or scenario.scenario_id
            ),
            run_id=scenario.scenario_id,
            workspace_id=str(downstream_input_manifest.get("workspace_id") or ""),
            scene=review_scene,
            source_kind="meeting_spatial_downstream_e2e",
            render_status="rendered" if clip_refs else "missing",
            renderer="video_renderer",
            clip_refs=clip_refs,
            context_metadata={
                "workspace_id": downstream_input_manifest.get("workspace_id"),
                "scene_id": downstream_input_manifest.get("scene_id"),
                "schedule_id": (
                    (scene_manifest.get("schedule_context_ref") or {}).get("schedule_id")
                ),
                "scenario_id": scenario.scenario_id,
                "artifact_ids": [
                    ((scene_manifest.get("schedule_context_ref") or {}).get("artifact_ref") or {}).get("artifact_id")
                ],
            },
        )
        render_slots = [
            slot for slot in list(bundle.get("slots") or []) if slot.get("slot") == "final_render"
        ]
        status = "materialized"
        if not render_slots:
            status = "missing_render_clips"
        elif not keyframe_entries or missing_keyframe_targets:
            status = "missing_keyframe_evidence"
        visual_acceptance_bundle_excerpt = {
            "status": status,
            "review_bundle_id": bundle.get("review_bundle_id"),
            "workspace_id": bundle.get("workspace_id"),
            "scene_id": bundle.get("scene_id"),
            "run_id": bundle.get("run_id"),
            "renderer": bundle.get("renderer"),
            "render_status": bundle.get("render_status"),
            "source_kind": bundle.get("source_kind"),
            "checklist_template": bundle.get("checklist_template"),
            "render_slots": render_slots,
            "keyframe_evidence": keyframe_entries,
            "required_targets": required_targets,
            "source_metadata": bundle.get("source_metadata"),
            "generated_at": bundle.get("created_at") or _now_utc(),
        }
        visual_acceptance_review_receipt = {
            "status": "pending_review" if status == "materialized" else "not_ready",
            "review_bundle_id": bundle.get("review_bundle_id"),
            "workspace_id": bundle.get("workspace_id"),
            "scene_id": bundle.get("scene_id"),
            "required_targets": required_targets,
            "missing_required_targets": missing_frame_targets,
            "clip_count": len(clip_refs),
            "keyframe_count": len(keyframe_entries),
            "generated_at": _now_utc(),
        }

    return {
        "motion_asset_manifest": motion_asset_manifest,
        "render_clip_manifest": render_clip_manifest,
        "keyframe_evidence_manifest": keyframe_evidence_manifest,
        "frame_beat_map": frame_beat_map,
        "visual_acceptance_bundle_excerpt": visual_acceptance_bundle_excerpt,
        "visual_acceptance_review_receipt": visual_acceptance_review_receipt,
    }


def _expand_path_tokens(value: str) -> str:
    result = value
    for token, replacement in _PATH_TOKEN_MAP.items():
        result = result.replace(token, str(replacement))
    return result


def _expand_path_tokens_in_payload(value: Any) -> Any:
    if isinstance(value, str):
        return _expand_path_tokens(value)
    if isinstance(value, list):
        return [_expand_path_tokens_in_payload(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _expand_path_tokens_in_payload(item) for key, item in value.items()
        }
    return value


def load_scenario_definition(path: Path) -> ScenarioDefinition:
    raw = path.read_text(encoding="utf-8")
    match = _SCENARIO_CONFIG_RE.search(raw)
    if not match:
        raise ValueError(f"Scenario file missing ```e2e_config block: {path}")
    config = json.loads(match.group("json"))
    if not isinstance(config, dict):
        raise ValueError(f"Scenario config must be a JSON object: {path}")
    config = _expand_path_tokens_in_payload(config)
    message = _SCENARIO_CONFIG_RE.sub("", raw).strip()
    if not message:
        message = str(config.get("meeting_message") or "").strip()
    if not message:
        raise ValueError(f"Scenario file missing meeting message body: {path}")
    return ScenarioDefinition(config=config, message=message)


async def _resolve_workspace_id(store: MindscapeStore, workspace_id: Optional[str]) -> str:
    if workspace_id:
        return workspace_id
    detected = _first_id(store, "workspaces")
    _must(bool(detected), "No workspace found. Provide --workspace-id.")
    return detected


async def _resolve_profile_id(store: MindscapeStore, profile_id: Optional[str]) -> str:
    candidate = profile_id or "default-user"
    if store.get_profile(candidate):
        return candidate
    detected = _first_id(store, "profiles")
    _must(bool(detected), "No profile found. Provide --profile-id.")
    return detected


def _ensure_thread(store: MindscapeStore, workspace_id: str, thread_id: Optional[str]) -> str:
    if thread_id:
        return thread_id

    default_thread = store.conversation_threads.get_default_thread(workspace_id)
    if default_thread:
        return default_thread.id

    existing = store.conversation_threads.list_threads_by_workspace(workspace_id, limit=1)
    if existing:
        return existing[0].id

    new_thread = ConversationThread(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title="Meeting Spatial Downstream E2E",
        project_id=None,
        created_at=_now_utc(),
        updated_at=_now_utc(),
        last_message_at=_now_utc(),
        message_count=0,
        metadata={"source": "meeting_spatial_downstream_e2e"},
        is_default=True,
    )
    store.conversation_threads.create_thread(new_thread)
    return new_thread.id


def _create_ephemeral_thread(
    store: MindscapeStore,
    *,
    workspace_id: str,
    title: str,
) -> str:
    new_thread = ConversationThread(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title=title,
        project_id=None,
        created_at=_now_utc(),
        updated_at=_now_utc(),
        last_message_at=_now_utc(),
        message_count=0,
        metadata={"source": "meeting_spatial_downstream_e2e", "ephemeral": True},
        is_default=False,
    )
    store.conversation_threads.create_thread(new_thread)
    return new_thread.id


def resolve_executor_runtime_binding(
    *,
    scenario: ScenarioDefinition,
    explicit_executor_runtime: Optional[str],
) -> Optional[str]:
    return _resolve_str_config(scenario, "executor_runtime", explicit_executor_runtime)


def probe_executor_runtime_availability(
    *,
    runtime_id: str,
    workspace_id: str,
) -> Dict[str, Any]:
    from backend.app.services.external_agents.core.registry import get_runtime_registry

    adapter = get_runtime_registry().get_adapter(runtime_id)
    _must(adapter is not None, f"Executor runtime adapter not found: {runtime_id}")
    detail = adapter.get_availability_detail(workspace_id=workspace_id)
    _must(
        bool(detail.get("available")),
        f"Executor runtime '{runtime_id}' unavailable for workspace '{workspace_id}': "
        f"{detail.get('reason')}",
    )
    return {
        "runtime_id": runtime_id,
        "workspace_id": workspace_id,
        "available": bool(detail.get("available")),
        "transport": detail.get("transport"),
        "reason": detail.get("reason"),
    }


def _should_use_direct_host_runtime_bridge(
    runtime_binding: Optional[Dict[str, Any]],
) -> bool:
    if not runtime_binding:
        return False
    runtime_id = str(runtime_binding.get("runtime_id") or "").strip()
    transport = str(runtime_binding.get("transport") or "").strip()
    return runtime_id in {"codex_cli", "claude_code_cli", "gemini_cli"} and transport == "polling"


def _patch_runtime_adapter_for_direct_host_execution(
    *,
    runtime_binding: Dict[str, Any],
) -> Callable[[], None]:
    from backend.app.services.external_agents.bridge.task_executor import (
        HostBridgeTaskExecutor,
    )
    from backend.app.services.external_agents.core.base_adapter import (
        RuntimeExecResponse,
    )
    from backend.app.services.external_agents.core.registry import get_runtime_registry

    runtime_id = str(runtime_binding.get("runtime_id") or "").strip()
    registry = get_runtime_registry()
    adapter = registry.get_adapter(runtime_id)
    _must(adapter is not None, f"Runtime adapter not found for direct host bridge: {runtime_id}")

    original_execute = adapter.execute

    async def _execute_direct(request: Any) -> RuntimeExecResponse:
        os.environ.setdefault("MINDSCAPE_BACKEND_API_URL", "http://localhost:8200")
        direct_executor = HostBridgeTaskExecutor(
            workspace_root=str(WORKSPACE_ROOT),
            runtime_surface=runtime_id,
            timeout=request.max_duration_seconds or 900,
        )
        execution_id = str(uuid.uuid4())
        started_at = time.monotonic()
        dispatch_msg = {
            "execution_id": execution_id,
            "workspace_id": request.workspace_id or runtime_binding.get("workspace_id") or "",
            "task": request.task,
            "allowed_tools": list(request.allowed_tools or ["file", "web_search"]),
            "max_duration": int(request.max_duration_seconds or 900),
            "model": str((request.agent_config or {}).get("model") or ""),
            "context": {
                "project_id": request.project_id or "",
                "intent_id": request.intent_id or "",
                "lens_id": request.lens_id or "",
                "sandbox_path": request.sandbox_path or "",
                "conversation_context": str(
                    (request.agent_config or {}).get("conversation_context") or ""
                ),
                "thread_id": str((request.agent_config or {}).get("thread_id") or ""),
                "auth_workspace_id": request.auth_workspace_id
                or request.workspace_id
                or "",
                "source_workspace_id": request.source_workspace_id
                or request.workspace_id
                or "",
                "control_action": str(
                    (request.agent_config or {}).get("control_action") or ""
                ),
                "uploaded_files": list(
                    (request.agent_config or {}).get("uploaded_files") or []
                ),
                "recommended_pack_codes": list(
                    (request.agent_config or {}).get("recommended_pack_codes") or []
                ),
                "file_hint": str((request.agent_config or {}).get("file_hint") or ""),
                "inputs": dict((request.agent_config or {}).get("inputs") or {}),
            },
        }
        result_dict = await direct_executor(dispatch_msg)
        duration = max(0.0, time.monotonic() - started_at)
        status = str(result_dict.get("status") or "")
        success = status == "completed"
        metadata = dict(result_dict.get("metadata") or {})
        metadata.setdefault("direct_host_runtime_bridge", True)
        metadata.setdefault("runtime_id", runtime_id)
        metadata.setdefault("execution_id", execution_id)
        return RuntimeExecResponse(
            success=success,
            output=str(result_dict.get("output") or ""),
            duration_seconds=duration,
            tool_calls=list(result_dict.get("tool_calls") or []),
            files_modified=list(result_dict.get("files_modified") or []),
            files_created=list(result_dict.get("files_created") or []),
            error=result_dict.get("error"),
            exit_code=0 if success else 1,
            agent_metadata=metadata,
        )

    adapter.execute = _execute_direct

    def _restore() -> None:
        adapter.execute = original_execute

    return _restore


def _apply_direct_host_runtime_env_overrides(
    runtime_binding: Optional[Dict[str, Any]],
) -> Callable[[], None]:
    if not _should_use_direct_host_runtime_bridge(runtime_binding):
        return lambda: None

    original_redis_enabled = os.environ.get("REDIS_ENABLED")
    os.environ["REDIS_ENABLED"] = "false"

    def _restore() -> None:
        if original_redis_enabled is None:
            os.environ.pop("REDIS_ENABLED", None)
            return
        os.environ["REDIS_ENABLED"] = original_redis_enabled

    return _restore


def _patch_dispatch_orchestrator_for_continuity_only() -> Callable[[], None]:
    from backend.app.services.orchestration.dispatch_orchestrator import (
        DispatchOrchestrator,
    )

    original_execute = DispatchOrchestrator.execute

    async def _execute_noop(self, task_ir: Any, action_items: Any) -> Dict[str, Any]:
        return {
            "phase_results": [],
            "skipped": True,
            "skip_reason": "e2e_continuity_only",
            "task_id": getattr(task_ir, "task_id", None),
            "action_item_count": len(action_items or []),
        }

    DispatchOrchestrator.execute = _execute_noop

    def _restore() -> None:
        DispatchOrchestrator.execute = original_execute

    return _restore


def build_handoff_request(
    *,
    scenario: ScenarioDefinition,
    workspace_id: str,
) -> HandoffIn:
    handoff_payload = dict(scenario.config.get("handoff_in") or {})
    handoff_payload.setdefault(
        "handoff_id", f"handoff_{scenario.scenario_id}_{uuid.uuid4().hex[:8]}"
    )
    handoff_payload.setdefault("workspace_id", workspace_id)
    handoff_payload.setdefault("intent_summary", scenario.message[:240])
    handoff_payload.setdefault(
        "requested_output_type", SPATIAL_SCHEDULE_ARTIFACT_MIME
    )
    governance_constraints = dict(handoff_payload.get("governance_constraints") or {})
    spatial_schedule = dict(governance_constraints.get("spatial_schedule") or {})
    spatial_schedule.setdefault("requested", True)
    if _resolve_bool_config(
        scenario,
        "require_full_deliberation_review",
        default=False,
    ):
        meeting_review = dict(governance_constraints.get("meeting_review") or {})
        meeting_review.setdefault("require_full_deliberation_review", True)
        meeting_review.setdefault("require_critic_turn", True)
        meeting_review.setdefault("disable_single_turn_native_pd", True)
        governance_constraints["meeting_review"] = meeting_review
    governance_constraints["spatial_schedule"] = spatial_schedule
    handoff_payload["governance_constraints"] = governance_constraints
    return HandoffIn(**handoff_payload)


def build_request_envelope(
    *,
    scenario: ScenarioDefinition,
    workspace_id: str,
) -> Any:
    handoff_in = build_handoff_request(scenario=scenario, workspace_id=workspace_id)
    return SimpleNamespace(
        handoff_in=handoff_in.model_dump(mode="json"),
        files=[],
    )


def extract_schedule_artifact_excerpt(
    *,
    task_ir_id: Optional[str],
    schedule_context: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = normalize_spatial_schedule_context(schedule_context)
    artifact_ref = dict(normalized.get("artifact_ref") or {})
    constraint_summary = dict(normalized.get("constraint_summary") or {})
    execution_plan = dict(
        (constraint_summary.get("native_execution_plan") or {})
    )
    return {
        "task_ir_id": task_ir_id,
        "schedule_id": normalized.get("schedule_id"),
        "schema_version": normalized.get("schema_version"),
        "status": normalized.get("status"),
        "artifact_ref": artifact_ref,
        "source_task_id": normalized.get("source_task_id"),
        "source_session_id": normalized.get("source_session_id"),
        "entity_kinds": list(normalized.get("entity_kinds") or []),
        "active_segments": list(normalized.get("active_segments") or []),
        "constraint_summary": constraint_summary,
        "execution_plan": execution_plan,
        "consumer_receipts": dict(normalized.get("consumer_receipts") or {}),
        "schedule_revision_refs": list(normalized.get("schedule_revision_refs") or []),
        "updated_at": normalized.get("updated_at"),
    }


def build_recompiled_schedule_bundle(
    *,
    scenario: ScenarioDefinition,
    session: Any,
    task_ir_id: Optional[str],
) -> Dict[str, Any]:
    handoff_payload = dict(scenario.config.get("handoff_in") or {})
    goals = list(handoff_payload.get("goals") or [])
    decision_summary = str(
        goals[0]
        if goals
        else handoff_payload.get("intent_summary") or scenario.message
    ).strip()
    governance = {
        "requested_output_type": handoff_payload.get(
            "requested_output_type", SPATIAL_SCHEDULE_ARTIFACT_MIME
        ),
        "intent_summary": decision_summary,
        "goals": goals,
        "deliverables": list(handoff_payload.get("deliverables") or []),
        "governance_constraints": dict(
            handoff_payload.get("governance_constraints") or {}
        ),
    }
    session_metadata = dict(getattr(session, "metadata", {}) or {})
    decision = str(
        decision_summary or getattr(session, "minutes_md", "")[:240] or scenario.message
    ).strip()
    source_task_id = str(
        task_ir_id
        or (session_metadata.get("spatial_schedule_context") or {}).get("source_task_id")
        or f"task_{scenario.scenario_id}_recompiled"
    )
    schedule = build_spatial_scheduling_ir(
        task_id=source_task_id,
        workspace_id=str(getattr(session, "workspace_id", "") or ""),
        session_id=str(getattr(session, "id", "") or ""),
        decision=decision,
        action_items=list(getattr(session, "action_items", []) or []),
        governance=governance,
        world_context=dict(session_metadata.get("world_memory_packet") or {}),
    )
    artifact = build_spatial_schedule_artifact(task_id=source_task_id, schedule=schedule)
    context = normalize_spatial_schedule_context(
        build_spatial_schedule_context(schedule=schedule, artifact=artifact)
    )
    return {
        "schedule": schedule.model_dump(mode="json"),
        "context": context,
        "excerpt": extract_schedule_artifact_excerpt(
            task_ir_id=source_task_id,
            schedule_context=context,
        ),
    }


def schedule_has_native_execution_plan(schedule_context: Dict[str, Any]) -> bool:
    normalized = normalize_spatial_schedule_context(schedule_context)
    if not normalized:
        return False
    constraint_summary = dict(normalized.get("constraint_summary") or {})
    native_execution_plan = dict(constraint_summary.get("native_execution_plan") or {})
    if not native_execution_plan:
        return False
    return any(
        native_execution_plan.get(key)
        for key in (
            "actors",
            "blocking_paths",
            "camera_blocking",
            "performance_beats",
            "interaction_beats",
        )
    )


def select_downstream_schedule_bundle(
    *,
    scenario: ScenarioDefinition,
    session_context: Dict[str, Any],
    schedule_artifact_excerpt: Dict[str, Any],
    recompiled_schedule_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    allow_schedule_recompile_fallback = bool(
        scenario.config.get("allow_schedule_recompile_fallback", True)
    )
    require_persisted_schedule_for_downstream = bool(
        scenario.config.get("require_persisted_schedule_for_downstream", False)
    )
    require_native_execution_plan = bool(
        scenario.config.get("require_native_execution_plan", False)
    )

    persisted_has_addressable_refs = schedule_context_has_addressable_refs(session_context)
    persisted_has_native_execution_plan = schedule_has_native_execution_plan(session_context)

    if require_native_execution_plan:
        _must(
            persisted_has_native_execution_plan,
            "Persisted session spatial_schedule_context missing native_execution_plan",
        )
    if require_persisted_schedule_for_downstream:
        _must(
            persisted_has_addressable_refs,
            "Persisted session spatial_schedule_context missing addressable refs",
        )
        return {
            "schedule_context": dict(session_context),
            "schedule_artifact_excerpt": dict(schedule_artifact_excerpt),
            "source": "persisted_session_context",
        }

    if persisted_has_addressable_refs:
        return {
            "schedule_context": dict(session_context),
            "schedule_artifact_excerpt": dict(schedule_artifact_excerpt),
            "source": "persisted_session_context",
        }

    recompiled_context = dict(recompiled_schedule_bundle.get("context") or {})
    recompiled_excerpt = dict(recompiled_schedule_bundle.get("excerpt") or {})
    if allow_schedule_recompile_fallback and schedule_context_has_addressable_refs(
        recompiled_context
    ):
        return {
            "schedule_context": recompiled_context,
            "schedule_artifact_excerpt": recompiled_excerpt,
            "source": "recompiled_from_session",
        }

    return {
        "schedule_context": dict(session_context),
        "schedule_artifact_excerpt": dict(schedule_artifact_excerpt),
        "source": "persisted_session_context",
    }


def build_execution_plan_artifacts(
    *,
    scenario: ScenarioDefinition,
    schedule_context: Dict[str, Any],
    schedule_artifact_excerpt: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    native_execution_plan = dict(
        schedule_artifact_excerpt.get("execution_plan")
        or (dict(schedule_artifact_excerpt.get("constraint_summary") or {}).get("native_execution_plan") or {})
        or (dict(schedule_context.get("constraint_summary") or {}).get("native_execution_plan") or {})
    )
    bounded_constraints = (
        dict(
            (((scenario.config.get("handoff_in") or {}).get("governance_constraints") or {})
            .get("spatial_schedule")
            or {})
        )
        .get("bounded_constraints")
        or {}
    )
    allow_scenario_fallback = bool(
        scenario.config.get("allow_scenario_execution_fallback", True)
    )
    schedule_id = str(
        schedule_artifact_excerpt.get("schedule_id")
        or schedule_context.get("schedule_id")
        or ""
    )
    source_session_id = str(schedule_context.get("source_session_id") or "")
    source_task_id = str(
        schedule_artifact_excerpt.get("source_task_id")
        or schedule_context.get("source_task_id")
        or ""
    )
    active_segments = [
        {
            "segment_id": str(segment.get("segment_id") or ""),
            "title": str(segment.get("title") or ""),
            "entity_refs": list(segment.get("entity_refs") or []),
            "anchor_ids": list(segment.get("anchor_ids") or []),
        }
        for segment in list(schedule_artifact_excerpt.get("active_segments") or [])
    ]
    execution_source = "native_execution_plan" if native_execution_plan else "missing"
    actors = list(native_execution_plan.get("actors") or [])
    blocking_paths = list(native_execution_plan.get("blocking_paths") or [])
    camera_blocking = list(native_execution_plan.get("camera_blocking") or [])
    performance_beats = list(native_execution_plan.get("performance_beats") or [])
    interaction_beats = list(native_execution_plan.get("interaction_beats") or [])
    if not native_execution_plan and allow_scenario_fallback:
        execution_source = "scenario_bounded_constraints"
        actors = list(bounded_constraints.get("actors") or [])
        blocking_paths = list(bounded_constraints.get("blocking_paths") or [])
        camera_blocking = list(bounded_constraints.get("camera_blocking") or [])
        performance_beats = list(bounded_constraints.get("performance_beats") or [])
        interaction_beats = list(bounded_constraints.get("interaction_beats") or [])
    shared = {
        "schedule_id": schedule_id,
        "source_session_id": source_session_id,
        "source_task_id": source_task_id,
        "artifact_ref": dict(schedule_artifact_excerpt.get("artifact_ref") or {}),
        "active_segments": active_segments,
        "execution_source": execution_source,
    }
    return {
        "blocking_plan_excerpt": {
            **shared,
            "actors": actors,
            "blocking_paths": blocking_paths,
        },
        "camera_blocking_manifest": {
            **shared,
            "camera_blocking": camera_blocking,
        },
        "performance_beats_excerpt": {
            **shared,
            "performance_beats": performance_beats,
            "interaction_beats": interaction_beats,
        },
    }


def count_meeting_role_turns(
    events: Sequence[Any],
    *,
    role_name: str,
) -> int:
    target_role = str(role_name or "").strip().lower()
    if not target_role:
        return 0
    total = 0
    for event in events:
        event_type_value = getattr(event, "event_type", None) or getattr(
            event, "type", None
        )
        if hasattr(event_type_value, "value"):
            event_type = str(getattr(event_type_value, "value") or "").strip().lower()
        else:
            event_type = str(event_type_value or "").strip().lower()
        if event_type != "agent_turn":
            continue
        payload = getattr(event, "payload", None) or {}
        if not isinstance(payload, dict):
            continue
        candidate_role = str(payload.get("role_name") or payload.get("role_id") or "").strip().lower()
        if candidate_role == target_role:
            total += 1
    return total


def schedule_context_has_addressable_refs(schedule_context: Dict[str, Any]) -> bool:
    normalized = normalize_spatial_schedule_context(schedule_context)
    if not normalized:
        return False
    if normalized.get("entity_kinds"):
        return True
    for segment in list(normalized.get("active_segments") or []):
        if list(segment.get("entity_refs") or []) or list(segment.get("anchor_ids") or []):
            return True
    return False


def validate_schedule_against_scenario(
    *,
    scenario: ScenarioDefinition,
    schedule_context: Dict[str, Any],
) -> None:
    expectations = dict(scenario.config.get("expected_schedule") or {})
    normalized = normalize_spatial_schedule_context(schedule_context)
    entity_kinds = set(normalized.get("entity_kinds") or [])
    required_entity_kinds = set(expectations.get("entity_kinds") or [])
    missing_entity_kinds = sorted(required_entity_kinds - entity_kinds)
    _must(
        not missing_entity_kinds,
        f"Schedule missing expected entity_kinds: {missing_entity_kinds}",
    )

    active_segments = list(normalized.get("active_segments") or [])
    min_segment_count = int(expectations.get("active_segment_count_min") or 0)
    if min_segment_count:
        _must(
            len(active_segments) >= min_segment_count,
            f"Expected at least {min_segment_count} active segments, got {len(active_segments)}",
        )

    required_anchor_ids = set(expectations.get("anchor_ids") or [])
    if required_anchor_ids:
        present_anchor_ids = {
            anchor_id
            for segment in active_segments
            for anchor_id in list(segment.get("anchor_ids") or [])
        }
        missing_anchor_ids = sorted(required_anchor_ids - present_anchor_ids)
        _must(
            not missing_anchor_ids,
            f"Schedule missing expected anchor_ids: {missing_anchor_ids}",
        )

    required_segment_titles = list(expectations.get("segment_titles") or [])
    if required_segment_titles:
        present_titles = {
            str(segment.get("title") or "").strip() for segment in active_segments
        }
        missing_titles = sorted(
            title for title in required_segment_titles if title not in present_titles
        )
        _must(
            not missing_titles,
            f"Schedule missing expected segment_titles: {missing_titles}",
        )

    required_consumer_hints = set(expectations.get("consumer_hints") or [])
    if required_consumer_hints:
        present_consumer_hints = set(
            normalized.get("constraint_summary", {}).get("consumer_hints") or []
        )
        missing_consumer_hints = sorted(
            required_consumer_hints - present_consumer_hints
        )
        _must(
            not missing_consumer_hints,
            f"Schedule missing expected consumer_hints: {missing_consumer_hints}",
        )

    required_intent_summary_contains = list(
        expectations.get("intent_summary_contains") or []
    )
    if required_intent_summary_contains:
        intent_summary = str(
            normalized.get("constraint_summary", {}).get("intent_summary") or ""
        )
        missing_fragments = sorted(
            fragment
            for fragment in required_intent_summary_contains
            if fragment not in intent_summary
        )
        _must(
            not missing_fragments,
            "Schedule intent_summary missing expected fragments: "
            f"{missing_fragments}",
        )


def build_downstream_input_manifest(
    *,
    scenario: ScenarioDefinition,
    schedule_context: Dict[str, Any],
    schedule_artifact_excerpt: Dict[str, Any],
    execution_artifacts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    validate_schedule_against_scenario(
        scenario=scenario,
        schedule_context=schedule_context,
    )
    downstream_seed = dict(scenario.config.get("downstream_seed") or {})
    scene_manifest = dict(downstream_seed.get("scene_manifest") or {})
    scene_manifest.setdefault(
        "scene_id", str(downstream_seed.get("scene_id") or scenario.scenario_id)
    )
    scene_manifest.setdefault("template_id", "vr_object_mesh_stage_proof_v1")
    scene_manifest.setdefault("output_type", "image")
    scene_manifest["schedule_context_ref"] = {
        "schedule_id": schedule_artifact_excerpt.get("schedule_id"),
        "artifact_ref": dict(schedule_artifact_excerpt.get("artifact_ref") or {}),
        "active_segments": list(schedule_artifact_excerpt.get("active_segments") or []),
        "constraint_summary": dict(
            schedule_artifact_excerpt.get("constraint_summary") or {}
        ),
    }
    execution_artifacts = execution_artifacts or {}
    if execution_artifacts.get("blocking_plan_excerpt"):
        scene_manifest["blocking_plan"] = dict(
            execution_artifacts["blocking_plan_excerpt"]
        )
    if execution_artifacts.get("camera_blocking_manifest"):
        scene_manifest["camera_blocking"] = dict(
            execution_artifacts["camera_blocking_manifest"]
        )
    if execution_artifacts.get("performance_beats_excerpt"):
        scene_manifest["performance_beats"] = dict(
            execution_artifacts["performance_beats_excerpt"]
        )
    return {
        "scenario_id": scenario.scenario_id,
        "workspace_id": str(downstream_seed.get("workspace_id") or ""),
        "scene_id": str(downstream_seed.get("scene_id") or scene_manifest["scene_id"]),
        "profile_id": str(downstream_seed.get("profile_id") or "vr_preview_local"),
        "tenant_id": str(
            downstream_seed.get("tenant_id") or "tenant_object_mesh_template"
        ),
        "target_content_root": downstream_seed.get("target_content_root"),
        "target_level_path": downstream_seed.get("target_level_path"),
        "scene_manifest": scene_manifest,
    }


def _import_cloud_runner(
    module_name: str,
    attr_name: str,
) -> Callable[..., Dict[str, Any]]:
    cloud_root = str(CLOUD_REPO)
    if cloud_root not in sys.path:
        sys.path.insert(0, cloud_root)
    module = __import__(module_name, fromlist=[attr_name])
    return getattr(module, attr_name)


async def run_downstream_chain(
    *,
    downstream_input_manifest: Dict[str, Any],
    cloud_output_root: Path,
    blender_runner: Optional[Callable[..., Dict[str, Any]]] = None,
    proof_runner: Optional[Callable[..., Dict[str, Any]]] = None,
    handoff_runner: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    blender_runner = blender_runner or _import_cloud_runner(
        "capabilities.blender_bridge.scripts.run_object_mesh_blender_preflight_bundle",
        "run_object_mesh_blender_preflight_bundle",
    )
    proof_runner = proof_runner or _import_cloud_runner(
        "capabilities.video_renderer.scripts.run_object_mesh_stage_proof_template",
        "arun_object_mesh_stage_proof_template",
    )
    handoff_runner = handoff_runner or _import_cloud_runner(
        "capabilities.ue5_runtime.scripts.run_video_renderer_object_mesh_world_import_handoff",
        "run_video_renderer_object_mesh_world_import_handoff",
    )
    cloud_output_root.mkdir(parents=True, exist_ok=True)
    input_manifest_path = cloud_output_root / "downstream_input_manifest.json"
    _write_json(input_manifest_path, downstream_input_manifest)

    blender_bundle_dir = cloud_output_root / "blender_preflight"
    proof_bundle_dir = cloud_output_root / "video_renderer_proof"
    handoff_bundle_dir = cloud_output_root / "world_import_handoff"
    blender_result = blender_runner(
        input_manifest_path=input_manifest_path,
        workspace_id=downstream_input_manifest["workspace_id"],
        scene_id=downstream_input_manifest["scene_id"],
        output_dir=blender_bundle_dir,
    )
    if inspect.isawaitable(blender_result):
        blender_result = await blender_result
    proof_result = proof_runner(
        input_manifest_path=input_manifest_path,
        workspace_id=downstream_input_manifest["workspace_id"],
        scene_id=downstream_input_manifest["scene_id"],
        output_dir=proof_bundle_dir,
        profile_id=downstream_input_manifest.get("profile_id"),
        tenant_id=downstream_input_manifest.get("tenant_id"),
    )
    if inspect.isawaitable(proof_result):
        proof_result = await proof_result
    handoff_result = handoff_runner(
        proof_bundle_dir=proof_bundle_dir,
        workspace_id=downstream_input_manifest["workspace_id"],
        scene_id=downstream_input_manifest["scene_id"],
        output_dir=handoff_bundle_dir,
        target_content_root=downstream_input_manifest.get("target_content_root"),
        target_level_path=downstream_input_manifest.get("target_level_path"),
        tenant_id=downstream_input_manifest.get("tenant_id")
        or "tenant_object_mesh_template",
    )
    if inspect.isawaitable(handoff_result):
        handoff_result = await handoff_result
    return {
        "input_manifest_path": str(input_manifest_path),
        "blender_result": blender_result,
        "proof_result": proof_result,
        "handoff_result": handoff_result,
    }


def build_truth_matrix(
    *,
    session: Any,
    session_context: Dict[str, Any],
    workspace_context: Dict[str, Any],
    governance_context: Dict[str, Any],
    world_memory_packet: Dict[str, Any],
    execution_artifacts: Dict[str, Dict[str, Any]],
    downstream_result: Dict[str, Any],
    motion_evidence: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    blender_result = dict(downstream_result.get("blender_result") or {})
    proof_result = dict(downstream_result.get("proof_result") or {})
    handoff_result = dict(downstream_result.get("handoff_result") or {})
    blocking_plan = dict(execution_artifacts.get("blocking_plan_excerpt") or {})
    camera_blocking = dict(execution_artifacts.get("camera_blocking_manifest") or {})
    performance_beats = dict(execution_artifacts.get("performance_beats_excerpt") or {})
    motion_evidence = motion_evidence or {}
    motion_asset_manifest = dict(motion_evidence.get("motion_asset_manifest") or {})
    render_clip_manifest = dict(motion_evidence.get("render_clip_manifest") or {})
    keyframe_evidence_manifest = dict(
        motion_evidence.get("keyframe_evidence_manifest") or {}
    )
    frame_beat_map = dict(motion_evidence.get("frame_beat_map") or {})
    visual_acceptance_bundle_excerpt = dict(
        motion_evidence.get("visual_acceptance_bundle_excerpt") or {}
    )
    visual_acceptance_review_receipt = dict(
        motion_evidence.get("visual_acceptance_review_receipt") or {}
    )
    execution_source = str(blocking_plan.get("execution_source") or "").strip()
    blender_preflight_continuity = bool(blender_result.get("bundle_dir")) and bool(
        blocking_plan.get("schedule_id")
    ) and bool(camera_blocking.get("schedule_id")) and bool(
        performance_beats.get("schedule_id")
    )
    stage_handoff_continuity = bool(
        proof_result.get("proof_bundle", {}).get("bundle_dir")
        or proof_result.get("resolved_output_dir")
    ) and bool(handoff_result.get("bundle_dir"))
    motion_asset_bundle_materialized = (
        motion_asset_manifest.get("status") == "materialized"
        and bool(list(motion_asset_manifest.get("motion_asset_refs") or []))
    )
    render_clip_materialized = (
        render_clip_manifest.get("status") == "materialized"
        and bool(list(render_clip_manifest.get("clip_refs") or []))
    )
    keyframe_evidence_materialized = (
        keyframe_evidence_manifest.get("status") == "materialized"
        and not list(keyframe_evidence_manifest.get("missing_required_targets") or [])
        and bool(list(keyframe_evidence_manifest.get("keyframe_evidence") or []))
    )
    visual_acceptance_bundle_materialized = (
        visual_acceptance_bundle_excerpt.get("status") == "materialized"
        and visual_acceptance_review_receipt.get("status") == "pending_review"
        and bool(list(visual_acceptance_bundle_excerpt.get("render_slots") or []))
    )
    script_to_motion_asset_continuity = (
        motion_asset_bundle_materialized
        and render_clip_materialized
        and keyframe_evidence_materialized
        and frame_beat_map.get("status") == "materialized"
        and not list(frame_beat_map.get("missing_required_targets") or [])
        and visual_acceptance_bundle_materialized
    )
    return {
        "scripted_meeting_session_closed": bool(
            getattr(getattr(session, "status", None), "value", None) == "closed"
        ),
        "spatial_schedule_context_persisted": bool(
            session_context.get("schedule_id") and workspace_context.get("schedule_id")
        ),
        "governance_schedule_context_readable": bool(
            governance_context.get("schedule_id")
        ),
        "world_sidecars_persisted": bool(
            world_memory_packet.get("active_schedule")
            and world_memory_packet["active_schedule"].get("schedule_id")
        ),
        "native_execution_plan_materialized": bool(
            execution_source == "native_execution_plan"
            and bool(blocking_plan.get("schedule_id"))
            and (
                list(blocking_plan.get("actors") or [])
                or list(blocking_plan.get("blocking_paths") or [])
                or list(camera_blocking.get("camera_blocking") or [])
                or list(performance_beats.get("performance_beats") or [])
                or list(performance_beats.get("interaction_beats") or [])
            )
        ),
        "scenario_execution_fallback_used": execution_source
        == "scenario_bounded_constraints",
        "blocking_plan_materialized": bool(
            blocking_plan.get("schedule_id")
            and list(blocking_plan.get("blocking_paths") or [])
        ),
        "camera_blocking_materialized": bool(
            camera_blocking.get("schedule_id")
            and list(camera_blocking.get("camera_blocking") or [])
        ),
        "performance_beats_materialized": bool(
            performance_beats.get("schedule_id")
            and (
                list(performance_beats.get("performance_beats") or [])
                or list(performance_beats.get("interaction_beats") or [])
            )
        ),
        "blender_preflight_bundle_materialized": bool(blender_result.get("bundle_dir")),
        "blender_preflight_continuity": blender_preflight_continuity,
        "blender_execution_continuity": blender_preflight_continuity,
        "downstream_stage_proof_bundle_materialized": bool(
            proof_result.get("proof_bundle", {}).get("bundle_dir")
            or proof_result.get("resolved_output_dir")
        ),
        "world_import_handoff_bundle_materialized": bool(
            handoff_result.get("bundle_dir")
        ),
        "motion_asset_bundle_materialized": motion_asset_bundle_materialized,
        "render_clip_materialized": render_clip_materialized,
        "keyframe_evidence_materialized": keyframe_evidence_materialized,
        "visual_acceptance_bundle_materialized": visual_acceptance_bundle_materialized,
        "downstream_schedule_used_recompiled_fallback": bool(
            handoff_result.get("meeting_schedule_source") == "recompiled_from_session"
        ),
        "stage_handoff_continuity": stage_handoff_continuity,
        "contract_continuity": stage_handoff_continuity,
        "script_to_motion_asset_continuity": script_to_motion_asset_continuity,
        "ue_importer_execution": False,
    }


def render_operator_report_html(
    *,
    scenario: ScenarioDefinition,
    output_dir: Path,
    meeting_session_receipt: Dict[str, Any],
    schedule_artifact_excerpt: Dict[str, Any],
    execution_artifacts: Dict[str, Dict[str, Any]],
    downstream_result: Dict[str, Any],
    motion_evidence_artifacts: Dict[str, Dict[str, Any]],
    truth_matrix: Dict[str, Any],
) -> str:
    blender_result = dict(downstream_result.get("blender_result") or {})
    proof_result = dict(downstream_result.get("proof_result") or {})
    handoff_result = dict(downstream_result.get("handoff_result") or {})
    blocking_plan = dict(execution_artifacts.get("blocking_plan_excerpt") or {})
    camera_blocking = dict(execution_artifacts.get("camera_blocking_manifest") or {})
    performance_beats = dict(execution_artifacts.get("performance_beats_excerpt") or {})
    motion_asset_manifest = dict(
        motion_evidence_artifacts.get("motion_asset_manifest") or {}
    )
    render_clip_manifest = dict(
        motion_evidence_artifacts.get("render_clip_manifest") or {}
    )
    keyframe_evidence_manifest = dict(
        motion_evidence_artifacts.get("keyframe_evidence_manifest") or {}
    )
    visual_acceptance_bundle_excerpt = dict(
        motion_evidence_artifacts.get("visual_acceptance_bundle_excerpt") or {}
    )
    execution_source = str(blocking_plan.get("execution_source") or "").strip() or "missing"
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Meeting Spatial Downstream E2E</title>
    <style>
      body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4efe6; color: #20170f; }}
      .page {{ max-width: 1080px; margin: 0 auto; padding: 40px 32px 64px; }}
      .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin: 24px 0; }}
      .card {{ background: #fff9f0; border: 1px solid #decfb8; border-radius: 16px; padding: 20px; }}
      .label {{ font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: #7a6851; }}
      .metric {{ font-size: 28px; font-weight: 700; margin-top: 6px; }}
      pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f1e4; border-radius: 12px; padding: 14px; }}
      h1, h2 {{ margin: 0 0 12px; }}
    </style>
  </head>
  <body>
    <div class="page">
      <h1>Meeting Spatial Downstream E2E</h1>
      <p>Scenario <code>{scenario.scenario_id}</code> materialized under <code>{output_dir}</code>.</p>
      <div class="grid">
        <section class="card">
          <div class="label">Meeting Session</div>
          <div class="metric">{meeting_session_receipt.get("meeting_session_id") or "n/a"}</div>
        </section>
        <section class="card">
          <div class="label">Schedule ID</div>
          <div class="metric">{schedule_artifact_excerpt.get("schedule_id") or "n/a"}</div>
        </section>
        <section class="card">
          <div class="label">Execution Source</div>
          <div class="metric">{execution_source}</div>
        </section>
        <section class="card">
          <div class="label">Blender Preflight</div>
          <div class="metric">{blender_result.get("bundle_dir") or "n/a"}</div>
        </section>
        <section class="card">
          <div class="label">Proof Bundle</div>
          <div class="metric">{proof_result.get("resolved_output_dir") or proof_result.get("proof_bundle", {}).get("bundle_dir") or "n/a"}</div>
        </section>
        <section class="card">
          <div class="label">World Handoff</div>
          <div class="metric">{handoff_result.get("bundle_dir") or "n/a"}</div>
        </section>
      </div>
      <section class="card">
        <h2>Truth Matrix</h2>
        <pre>{json.dumps(truth_matrix, indent=2, ensure_ascii=False)}</pre>
      </section>
      <section class="card">
        <h2>Blocking Plan</h2>
        <pre>{json.dumps(blocking_plan, indent=2, ensure_ascii=False)}</pre>
      </section>
      <section class="card">
        <h2>Camera Blocking</h2>
        <pre>{json.dumps(camera_blocking, indent=2, ensure_ascii=False)}</pre>
      </section>
      <section class="card">
        <h2>Performance Beats</h2>
        <pre>{json.dumps(performance_beats, indent=2, ensure_ascii=False)}</pre>
      </section>
      <section class="card">
        <h2>Blender Preflight</h2>
        <pre>{json.dumps(blender_result, indent=2, ensure_ascii=False)}</pre>
      </section>
      <section class="card">
        <h2>Motion Asset Manifest</h2>
        <pre>{json.dumps(motion_asset_manifest, indent=2, ensure_ascii=False, default=_json_default)}</pre>
      </section>
      <section class="card">
        <h2>Render Clip Manifest</h2>
        <pre>{json.dumps(render_clip_manifest, indent=2, ensure_ascii=False, default=_json_default)}</pre>
      </section>
      <section class="card">
        <h2>Keyframe Evidence Manifest</h2>
        <pre>{json.dumps(keyframe_evidence_manifest, indent=2, ensure_ascii=False, default=_json_default)}</pre>
      </section>
      <section class="card">
        <h2>Visual Acceptance Bundle</h2>
        <pre>{json.dumps(visual_acceptance_bundle_excerpt, indent=2, ensure_ascii=False, default=_json_default)}</pre>
      </section>
    </div>
  </body>
</html>
"""


def _derive_runtime_blocker_code(error_text: str) -> str:
    normalized = str(error_text or "").lower()
    if "usage limit" in normalized or "capacity" in normalized:
        return "codex_cli_usage_limit"
    if "not supported when using codex" in normalized:
        return "codex_cli_model_unsupported"
    if "executor runtime" in normalized and "unavailable" in normalized:
        return "codex_cli_unavailable"
    return "meeting_pipeline_failed"


def _write_runtime_blocker_bundle(
    *,
    scenario: ScenarioDefinition,
    output_dir: Path,
    workspace_id: str,
    profile_id: Optional[str],
    thread_id: Optional[str],
    runtime_binding: Optional[Dict[str, Any]],
    error_text: str,
    meeting_session_id: Optional[str] = None,
    session: Optional[Any] = None,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_text(output_dir / "meeting_input.md", scenario.message)
    _write_json(output_dir / "meeting_runtime_binding.json", runtime_binding or {})

    blocker_payload = {
        "scenario_id": scenario.scenario_id,
        "workspace_id": workspace_id,
        "profile_id": profile_id,
        "thread_id": thread_id,
        "meeting_session_id": meeting_session_id,
        "runtime_id": str((runtime_binding or {}).get("runtime_id") or "codex_cli"),
        "transport": (runtime_binding or {}).get("transport"),
        "delivery_mode": (runtime_binding or {}).get("delivery_mode"),
        "blocker_code": _derive_runtime_blocker_code(error_text),
        "error": error_text,
        "session_status": (
            getattr(getattr(session, "status", None), "value", None) if session else None
        ),
        "round_count": getattr(session, "round_count", None) if session else None,
        "ended_at": getattr(session, "ended_at", None) if session else None,
        "pipeline_stage": (
            dict(getattr(session, "metadata", {}) or {}).get("pipeline_stage")
            if session
            else None
        ),
        "generated_at": _now_utc(),
    }
    _write_json(output_dir / "runtime_blocker.json", blocker_payload)

    report_html = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Meeting Native E2E Runtime Blocker</title>
    <style>
      body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4efe6; color: #20170f; }}
      .page {{ max-width: 1080px; margin: 0 auto; padding: 40px 32px 64px; }}
      .card {{ background: #fff9f0; border: 1px solid #decfb8; border-radius: 16px; padding: 20px; margin-bottom: 20px; }}
      .label {{ font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: #7a6851; }}
      .metric {{ font-size: 28px; font-weight: 700; margin-top: 6px; }}
      pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f1e4; border-radius: 12px; padding: 14px; }}
      h1, h2 {{ margin: 0 0 12px; }}
    </style>
  </head>
  <body>
    <div class="page">
      <h1>Meeting Native E2E Runtime Blocker</h1>
      <div class="card">
        <div class="label">Scenario</div>
        <div class="metric">{scenario.scenario_id}</div>
      </div>
      <div class="card">
        <div class="label">Blocker Code</div>
        <div class="metric">{blocker_payload["blocker_code"]}</div>
      </div>
      <div class="card">
        <div class="label">Workspace</div>
        <div class="metric">{workspace_id}</div>
      </div>
      <div class="card">
        <div class="label">Meeting Session</div>
        <div class="metric">{meeting_session_id or "n/a"}</div>
      </div>
      <div class="card">
        <h2>Runtime Binding</h2>
        <pre>{json.dumps(runtime_binding or {{}}, indent=2, ensure_ascii=False, default=_json_default)}</pre>
      </div>
      <div class="card">
        <h2>Error</h2>
        <pre>{error_text}</pre>
      </div>
    </div>
  </body>
</html>
"""
    _write_text(output_dir / "operator_report.html", report_html)
    return blocker_payload


async def run_meeting_spatial_downstream_e2e(
    *,
    scenario_file: Path,
    output_dir: Path,
    meeting_session_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    project_id: Optional[str] = None,
    model_name: Optional[str] = None,
    executor_runtime: Optional[str] = None,
    require_motion_evidence: bool = False,
    emit_visual_acceptance_bundle: bool = False,
    skip_phase_dispatch: Optional[bool] = None,
    max_events: int = 500,
    proof_runner: Optional[Callable[..., Dict[str, Any]]] = None,
    handoff_runner: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    scenario = load_scenario_definition(scenario_file)
    store = MindscapeStore()
    session_store = MeetingSessionStore()
    runtime_binding: Optional[Dict[str, Any]] = None
    output_dir.mkdir(parents=True, exist_ok=True)

    if meeting_session_id:
        session = session_store.get_by_id(meeting_session_id)
        _must(session is not None, f"MeetingSession not found: {meeting_session_id}")
        _must(
            getattr(session.status, "value", None) == "closed",
            f"Meeting session not closed: {meeting_session_id}",
        )
        workspace_id = workspace_id or str(getattr(session, "workspace_id", "") or "")
        _must(workspace_id, "Workspace ID missing for existing meeting session")
        workspace = await store.get_workspace(workspace_id)
        _must(workspace is not None, f"Workspace not found: {workspace_id}")
        profile_id = profile_id or _resolve_str_config(scenario, "profile_id", profile_id)
        thread_id = thread_id or getattr(session, "thread_id", None)
        resolved_project_id = project_id or getattr(session, "project_id", None)
        task_ir_id = (
            dict(getattr(session, "metadata", {}) or {})
            .get("spatial_schedule_context", {})
            .get("source_task_id")
        )
    else:
        workspace_id = await _resolve_workspace_id(
            store, _resolve_str_config(scenario, "workspace_id", workspace_id)
        )
        profile_id = await _resolve_profile_id(
            store, _resolve_str_config(scenario, "profile_id", profile_id)
        )
        force_fresh_thread = _resolve_bool_config(
            scenario,
            "force_fresh_thread",
            default=bool(
                _resolve_bool_config(
                    scenario,
                    "require_native_execution_plan",
                    default=False,
                )
            ),
        )
        if not thread_id and force_fresh_thread:
            thread_id = _create_ephemeral_thread(
                store,
                workspace_id=workspace_id,
                title=f"Meeting Spatial Downstream E2E · {scenario.scenario_id}",
            )
        elif not thread_id:
            thread_id = _ensure_thread(store, workspace_id, thread_id)

        workspace = await store.get_workspace(workspace_id)
        _must(workspace is not None, f"Workspace not found: {workspace_id}")
        profile = store.get_profile(profile_id)
        _must(profile is not None, f"Profile not found: {profile_id}")

        resolved_executor_runtime = resolve_executor_runtime_binding(
            scenario=scenario,
            explicit_executor_runtime=executor_runtime,
        )
        if resolved_executor_runtime:
            runtime_binding = probe_executor_runtime_availability(
                runtime_id=resolved_executor_runtime,
                workspace_id=workspace_id,
            )
            setattr(workspace, "executor_runtime", resolved_executor_runtime)

        runtime_store = WorkspaceRuntimeProfileStore(db_path=store.db_path)
        runtime_profile = await runtime_store.get_runtime_profile(workspace_id)
        if not runtime_profile:
            runtime_profile = await runtime_store.create_default_profile(workspace_id)

        resolved_project_id = project_id
        if not resolved_project_id and getattr(workspace, "primary_project_id", None):
            resolved_project_id = workspace.primary_project_id

        user_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_now_utc(),
            actor=EventActor.USER,
            channel="local_workspace",
            profile_id=profile_id,
            project_id=resolved_project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload={"message": scenario.message, "mode": "meeting"},
            entity_ids=[],
            metadata={"e2e_test": True, "source": "meeting_spatial_downstream_e2e"},
        )
        store.create_event(user_event)

        restore_runtime_adapter: Optional[Callable[[], None]] = None
        restore_dispatch_orchestrator: Optional[Callable[[], None]] = None
        restore_runtime_env: Optional[Callable[[], None]] = None
        if _should_use_direct_host_runtime_bridge(runtime_binding):
            runtime_binding["delivery_mode"] = "direct_host_runtime_bridge"
            restore_runtime_env = _apply_direct_host_runtime_env_overrides(
                runtime_binding
            )
            restore_runtime_adapter = _patch_runtime_adapter_for_direct_host_execution(
                runtime_binding=runtime_binding
            )
        if _resolve_bool_config(
            scenario,
            "skip_phase_dispatch",
            skip_phase_dispatch,
            default=True,
        ):
            restore_dispatch_orchestrator = (
                _patch_dispatch_orchestrator_for_continuity_only()
            )

        try:
            pipeline = PipelineCore(
                orchestrator_store=store,
                workspace=workspace,
                profile=profile,
                runtime_profile=runtime_profile,
            )
            result = await pipeline.process(
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                project_id=resolved_project_id,
                message=scenario.message,
                user_event_id=user_event.id,
                execution_mode="meeting",
                model_name=model_name,
                request=build_request_envelope(
                    scenario=scenario, workspace_id=workspace_id
                ),
            )
        finally:
            if restore_dispatch_orchestrator is not None:
                restore_dispatch_orchestrator()
            if restore_runtime_adapter is not None:
                restore_runtime_adapter()
            if restore_runtime_env is not None:
                restore_runtime_env()
        if not result.success or not result.meeting_session_id:
            blocker_session_id = getattr(result, "meeting_session_id", None)
            blocker_session = (
                session_store.get_by_id(blocker_session_id)
                if blocker_session_id
                else None
            )
            _write_runtime_blocker_bundle(
                scenario=scenario,
                output_dir=output_dir,
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                runtime_binding=runtime_binding,
                error_text=str(
                    result.error
                    or "meeting_session_id missing in PipelineResult"
                ),
                meeting_session_id=blocker_session_id,
                session=blocker_session,
            )
            _must(result.success, f"PipelineCore failed: {result.error}")
            _must(
                bool(result.meeting_session_id),
                "meeting_session_id missing in PipelineResult",
            )

        session = session_store.get_by_id(result.meeting_session_id)
        if session is None or getattr(session.status, "value", None) != "closed":
            _write_runtime_blocker_bundle(
                scenario=scenario,
                output_dir=output_dir,
                workspace_id=workspace_id,
                profile_id=profile_id,
                thread_id=thread_id,
                runtime_binding=runtime_binding,
                error_text="Meeting session not closed",
                meeting_session_id=result.meeting_session_id,
                session=session,
            )
            _must(session is not None, "MeetingSession not found after run")
            _must(
                getattr(session.status, "value", None) == "closed",
                "Meeting session not closed",
            )
        meeting_session_id = result.meeting_session_id
        task_ir_id = result.task_ir_id

    events = store.get_events_by_meeting_session(
        meeting_session_id=meeting_session_id,
        workspace_id=workspace_id,
        limit=max_events,
    )
    critic_turn_count = count_meeting_role_turns(events, role_name="critic")
    require_full_deliberation_review = _resolve_bool_config(
        scenario,
        "require_full_deliberation_review",
        default=False,
    )
    if require_full_deliberation_review:
        _must(critic_turn_count > 0, "Meeting session missing critic turn")
    session_context = normalize_spatial_schedule_context(
        dict(getattr(session, "metadata", {}) or {}).get("spatial_schedule_context")
    )
    _must(session_context is not None, "Session missing spatial_schedule_context")

    workspace = await store.get_workspace(workspace_id)
    workspace_context = normalize_spatial_schedule_context(
        dict(getattr(workspace, "metadata", {}) or {}).get("spatial_schedule_context")
    )
    _must(workspace_context is not None, "Workspace missing spatial_schedule_context")

    governance_packet = await GovernanceContextReadModel(
        store=store,
        meeting_session_store=session_store,
    ).build_for_workspace(workspace, session_id=meeting_session_id)
    _must(governance_packet is not None, "Governance packet unavailable")
    governance_context = dict(
        (governance_packet.get("governance_context") or {}).get(
            "spatial_schedule_context"
        )
        or {}
    )
    _must(governance_context, "Governance packet missing spatial_schedule_context")

    world_memory_packet = dict(getattr(session, "metadata", {}) or {}).get(
        "world_memory_packet"
    ) or {}
    world_card_projection = dict(getattr(session, "metadata", {}) or {}).get(
        "world_card_projection"
    ) or {}

    output_dir.mkdir(parents=True, exist_ok=True)
    schedule_artifact_excerpt = extract_schedule_artifact_excerpt(
        task_ir_id=task_ir_id,
        schedule_context=session_context,
    )
    recompiled_schedule_bundle = build_recompiled_schedule_bundle(
        scenario=scenario,
        session=session,
        task_ir_id=task_ir_id,
    )
    downstream_schedule_bundle = select_downstream_schedule_bundle(
        scenario=scenario,
        session_context=session_context,
        schedule_artifact_excerpt=schedule_artifact_excerpt,
        recompiled_schedule_bundle=recompiled_schedule_bundle,
    )
    downstream_schedule_context = dict(
        downstream_schedule_bundle["schedule_context"]
    )
    downstream_schedule_artifact_excerpt = dict(
        downstream_schedule_bundle["schedule_artifact_excerpt"]
    )
    downstream_schedule_source = str(
        downstream_schedule_bundle.get("source") or "persisted_session_context"
    )
    execution_artifacts = build_execution_plan_artifacts(
        scenario=scenario,
        schedule_context=downstream_schedule_context,
        schedule_artifact_excerpt=downstream_schedule_artifact_excerpt,
    )
    downstream_input_manifest = build_downstream_input_manifest(
        scenario=scenario,
        schedule_context=downstream_schedule_context,
        schedule_artifact_excerpt=downstream_schedule_artifact_excerpt,
        execution_artifacts=execution_artifacts,
    )
    cloud_output_root = CLOUD_REPO / ".tmp" / "meeting-spatial-downstream-e2e" / output_dir.name
    downstream_result = await run_downstream_chain(
        downstream_input_manifest=downstream_input_manifest,
        cloud_output_root=cloud_output_root,
        proof_runner=proof_runner,
        handoff_runner=handoff_runner,
    )
    downstream_result["meeting_schedule_source"] = downstream_schedule_source
    motion_evidence_artifacts = build_motion_evidence_artifacts(
        scenario=scenario,
        downstream_input_manifest=downstream_input_manifest,
        execution_artifacts=execution_artifacts,
        downstream_result=downstream_result,
        emit_visual_acceptance_bundle=emit_visual_acceptance_bundle,
    )

    meeting_session_receipt = {
        "workspace_id": workspace_id,
        "profile_id": profile_id,
        "thread_id": thread_id,
        "meeting_session_id": meeting_session_id,
        "task_ir_id": task_ir_id,
        "round_count": getattr(session, "round_count", None),
        "status": getattr(getattr(session, "status", None), "value", None),
        "action_item_count": len(getattr(session, "action_items", []) or []),
        "event_count": len(events),
        "critic_turn_count": critic_turn_count,
        "require_full_deliberation_review": require_full_deliberation_review,
        "downstream_schedule_source": downstream_schedule_source,
    }
    meeting_script_outline = [
        {
            "title": item.get("title"),
            "description": item.get("description"),
            "priority": item.get("priority"),
            "blocked_by": list(item.get("blocked_by") or []),
            "target_workspace_id": item.get("target_workspace_id"),
        }
        for item in list(getattr(session, "action_items", []) or [])
    ]
    truth_matrix = build_truth_matrix(
        session=session,
        session_context=session_context,
        workspace_context=workspace_context,
        governance_context=governance_context,
        world_memory_packet=world_memory_packet,
        execution_artifacts=execution_artifacts,
        downstream_result=downstream_result,
        motion_evidence=motion_evidence_artifacts,
    )

    _write_text(output_dir / "meeting_input.md", scenario.message)
    _write_json(output_dir / "meeting_session_receipt.json", meeting_session_receipt)
    _write_json(output_dir / "meeting_runtime_binding.json", runtime_binding or {})
    _write_json(output_dir / "meeting_action_items.json", list(getattr(session, "action_items", []) or []))
    _write_json(output_dir / "meeting_script_outline.json", meeting_script_outline)
    _write_text(output_dir / "meeting_minutes.md", getattr(session, "minutes_md", "") or "")
    _write_json(output_dir / "schedule_artifact_excerpt.json", schedule_artifact_excerpt)
    _write_json(output_dir / "spatial_schedule_context.json", session_context)
    _write_json(
        output_dir / "schedule_artifact_recompiled.json",
        recompiled_schedule_bundle.get("schedule") or {},
    )
    _write_json(
        output_dir / "schedule_artifact_excerpt_recompiled.json",
        recompiled_schedule_bundle.get("excerpt") or {},
    )
    _write_json(
        output_dir / "spatial_schedule_context_recompiled.json",
        recompiled_schedule_bundle.get("context") or {},
    )
    _write_json(output_dir / "workspace_schedule_context.json", workspace_context)
    _write_json(
        output_dir / "governance_schedule_context_excerpt.json", governance_context
    )
    _write_json(output_dir / "world_memory_packet_excerpt.json", world_memory_packet)
    _write_json(output_dir / "world_card_projection_excerpt.json", world_card_projection)
    _write_json(
        output_dir / "blocking_plan_excerpt.json",
        execution_artifacts.get("blocking_plan_excerpt") or {},
    )
    _write_json(
        output_dir / "camera_blocking_manifest.json",
        execution_artifacts.get("camera_blocking_manifest") or {},
    )
    _write_json(
        output_dir / "performance_beats_excerpt.json",
        execution_artifacts.get("performance_beats_excerpt") or {},
    )
    _write_json(output_dir / "downstream_input_manifest.json", downstream_input_manifest)
    _write_json(
        output_dir / "blender_preflight_receipt.json",
        downstream_result.get("blender_result") or {},
    )
    _write_json(
        output_dir / "downstream_stage_proof_receipt.json",
        downstream_result.get("proof_result") or {},
    )
    _write_json(
        output_dir / "world_import_handoff_receipt.json",
        downstream_result.get("handoff_result") or {},
    )
    _write_json(
        output_dir / "motion_asset_manifest.json",
        motion_evidence_artifacts.get("motion_asset_manifest") or {},
    )
    _write_json(
        output_dir / "render_clip_manifest.json",
        motion_evidence_artifacts.get("render_clip_manifest") or {},
    )
    _write_json(
        output_dir / "keyframe_evidence_manifest.json",
        motion_evidence_artifacts.get("keyframe_evidence_manifest") or {},
    )
    _write_json(
        output_dir / "frame_beat_map.json",
        motion_evidence_artifacts.get("frame_beat_map") or {},
    )
    _write_json(
        output_dir / "visual_acceptance_bundle_excerpt.json",
        motion_evidence_artifacts.get("visual_acceptance_bundle_excerpt") or {},
    )
    _write_json(
        output_dir / "visual_acceptance_review_receipt.json",
        motion_evidence_artifacts.get("visual_acceptance_review_receipt") or {},
    )
    _write_json(output_dir / "e2e_truth_matrix.json", truth_matrix)
    report_html = render_operator_report_html(
        scenario=scenario,
        output_dir=output_dir,
        meeting_session_receipt=meeting_session_receipt,
        schedule_artifact_excerpt=schedule_artifact_excerpt,
        execution_artifacts=execution_artifacts,
        downstream_result=downstream_result,
        motion_evidence_artifacts=motion_evidence_artifacts,
        truth_matrix=truth_matrix,
    )
    _write_text(output_dir / "operator_report.html", report_html)
    if require_motion_evidence:
        _must(
            bool(truth_matrix.get("script_to_motion_asset_continuity")),
            "Motion evidence gate failed",
        )

    return {
        "scenario_id": scenario.scenario_id,
        "output_dir": str(output_dir),
        "cloud_output_root": str(cloud_output_root),
        "meeting_session_receipt": meeting_session_receipt,
        "meeting_runtime_binding": runtime_binding or {},
        "truth_matrix": truth_matrix,
    }
