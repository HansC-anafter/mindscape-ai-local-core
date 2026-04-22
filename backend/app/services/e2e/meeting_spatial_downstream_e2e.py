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
from typing import Any, Callable, Dict, Optional, Sequence

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
        "constraint_summary": dict(normalized.get("constraint_summary") or {}),
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


def build_execution_plan_artifacts(
    *,
    scenario: ScenarioDefinition,
    schedule_context: Dict[str, Any],
    schedule_artifact_excerpt: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    bounded_constraints = (
        dict(
            (((scenario.config.get("handoff_in") or {}).get("governance_constraints") or {})
            .get("spatial_schedule")
            or {})
        )
        .get("bounded_constraints")
        or {}
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
    shared = {
        "schedule_id": schedule_id,
        "source_session_id": source_session_id,
        "source_task_id": source_task_id,
        "artifact_ref": dict(schedule_artifact_excerpt.get("artifact_ref") or {}),
        "active_segments": active_segments,
    }
    return {
        "blocking_plan_excerpt": {
            **shared,
            "actors": list(bounded_constraints.get("actors") or []),
            "blocking_paths": list(bounded_constraints.get("blocking_paths") or []),
        },
        "camera_blocking_manifest": {
            **shared,
            "camera_blocking": list(bounded_constraints.get("camera_blocking") or []),
        },
        "performance_beats_excerpt": {
            **shared,
            "performance_beats": list(bounded_constraints.get("performance_beats") or []),
            "interaction_beats": list(bounded_constraints.get("interaction_beats") or []),
        },
    }


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
) -> Dict[str, Any]:
    blender_result = dict(downstream_result.get("blender_result") or {})
    proof_result = dict(downstream_result.get("proof_result") or {})
    handoff_result = dict(downstream_result.get("handoff_result") or {})
    blocking_plan = dict(execution_artifacts.get("blocking_plan_excerpt") or {})
    camera_blocking = dict(execution_artifacts.get("camera_blocking_manifest") or {})
    performance_beats = dict(execution_artifacts.get("performance_beats_excerpt") or {})
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
        "blender_execution_continuity": bool(blender_result.get("bundle_dir"))
        and bool(blocking_plan.get("schedule_id"))
        and bool(camera_blocking.get("schedule_id"))
        and bool(performance_beats.get("schedule_id")),
        "downstream_stage_proof_bundle_materialized": bool(
            proof_result.get("proof_bundle", {}).get("bundle_dir")
            or proof_result.get("resolved_output_dir")
        ),
        "world_import_handoff_bundle_materialized": bool(
            handoff_result.get("bundle_dir")
        ),
        "contract_continuity": bool(
            proof_result.get("proof_bundle", {}).get("bundle_dir")
            or proof_result.get("resolved_output_dir")
        )
        and bool(handoff_result.get("bundle_dir")),
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
    truth_matrix: Dict[str, Any],
) -> str:
    blender_result = dict(downstream_result.get("blender_result") or {})
    proof_result = dict(downstream_result.get("proof_result") or {})
    handoff_result = dict(downstream_result.get("handoff_result") or {})
    blocking_plan = dict(execution_artifacts.get("blocking_plan_excerpt") or {})
    camera_blocking = dict(execution_artifacts.get("camera_blocking_manifest") or {})
    performance_beats = dict(execution_artifacts.get("performance_beats_excerpt") or {})
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
    </div>
  </body>
</html>
"""


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
    skip_phase_dispatch: Optional[bool] = None,
    max_events: int = 500,
    proof_runner: Optional[Callable[..., Dict[str, Any]]] = None,
    handoff_runner: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    scenario = load_scenario_definition(scenario_file)
    store = MindscapeStore()
    session_store = MeetingSessionStore()
    runtime_binding: Optional[Dict[str, Any]] = None

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
        if _should_use_direct_host_runtime_bridge(runtime_binding):
            runtime_binding["delivery_mode"] = "direct_host_runtime_bridge"
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
        _must(result.success, f"PipelineCore failed: {result.error}")
        _must(
            bool(result.meeting_session_id), "meeting_session_id missing in PipelineResult"
        )

        session = session_store.get_by_id(result.meeting_session_id)
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
    downstream_schedule_context = session_context
    downstream_schedule_artifact_excerpt = schedule_artifact_excerpt
    if schedule_context_has_addressable_refs(
        recompiled_schedule_bundle.get("context") or {}
    ):
        downstream_schedule_context = dict(recompiled_schedule_bundle["context"])
        downstream_schedule_artifact_excerpt = dict(recompiled_schedule_bundle["excerpt"])
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
        "downstream_schedule_source": (
            "recompiled_from_session"
            if downstream_schedule_context is not session_context
            else "persisted_session_context"
        ),
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
    _write_json(output_dir / "e2e_truth_matrix.json", truth_matrix)
    report_html = render_operator_report_html(
        scenario=scenario,
        output_dir=output_dir,
        meeting_session_receipt=meeting_session_receipt,
        schedule_artifact_excerpt=schedule_artifact_excerpt,
        execution_artifacts=execution_artifacts,
        downstream_result=downstream_result,
        truth_matrix=truth_matrix,
    )
    _write_text(output_dir / "operator_report.html", report_html)

    return {
        "scenario_id": scenario.scenario_id,
        "output_dir": str(output_dir),
        "cloud_output_root": str(cloud_output_root),
        "meeting_session_receipt": meeting_session_receipt,
        "meeting_runtime_binding": runtime_binding or {},
        "truth_matrix": truth_matrix,
    }
