"""Object runtime service helpers extracted from the route facade."""

from __future__ import annotations

import importlib
import inspect
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, Path as PathParam, Query
from fastapi.encoders import jsonable_encoder

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.object_runtime import (
    MeetingAttachmentSummary,
    ObjectAction,
    ObjectActionClosureRequest,
    ObjectActionClosureResponse,
    ObjectActionInvokeRequest,
    ObjectActionInvokeResponse,
    ObjectActionPlanRequest,
    ObjectActionPlanResponse,
    ObjectAffordanceCapability,
    ObjectCatalogEntry,
    ObjectCatalogResponse,
    ObjectGraphProjectRequest,
    ObjectGraphProjectResponse,
    ObjectGraphProjection,
    ObjectGraphProjectionCapabilities,
    ObjectGraphRelation,
    ObjectGuidanceCard,
    ObjectInstanceIndexRequest,
    ObjectInstanceIndexResponse,
    ObjectInstanceRecord,
    ObjectInstanceSyncRequest,
    ObjectInstanceSyncResponse,
    ObjectMaterializeRequest,
    ObjectMaterializeResponse,
    ObjectMaterializerCapabilities,
    ObjectMeetingAttachRequest,
    ObjectMeetingAttachResponse,
    ObjectMeetingProjectionCapabilities,
    ObjectMentionCompletionItem,
    ObjectMentionCompletionResponse,
    ObjectReadRequest,
    ObjectReadResponse,
    ObjectRef,
    ObjectRelationIndexRequest,
    ObjectRelationIndexResponse,
    ObjectRelationRecord,
    ObjectRelationSearchResponse,
    ObjectResolverCapabilities,
    ObjectRoleEntry,
    ObjectSearchResponse,
    ObjectSummary,
    ResolvedSelectionObject,
    SelectionResolveError,
    SelectionResolveRequest,
    SelectionResolveResponse,
)
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.object_catalog_registry import ObjectCatalogRegistry
from backend.app.services.object_index_sync_service import (
    get_object_index_sync_service,
    get_object_index_sync_status,
)
from backend.app.services.object_meeting_attachment_service import (
    ObjectMeetingAttachmentService,
    ObjectMeetingContextRecord,
)
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.object_instance_registry_store import ObjectInstanceRegistryStore
from backend.app.services.stores.object_relation_registry_store import ObjectRelationRegistryStore
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)

from backend.app.services.object_runtime.common import *
from backend.app.services.object_runtime.dependencies import *

def _entry_supports_affordance(
    entry_payload: Dict[str, Any],
    affordance: Dict[str, Any],
) -> bool:
    object_kinds = list(affordance.get("object_kinds") or [])
    if not object_kinds:
        return True
    return _text(entry_payload.get("object_kind")) in object_kinds

def _select_action_affordance(
    entry_payloads: List[Dict[str, Any]],
    *,
    requested_verb: str | None,
    present_roles: set[str],
) -> Tuple[Dict[str, Any] | None, List[str]]:
    candidates: List[Dict[str, Any]] = []
    for entry_payload in entry_payloads:
        for affordance in list(entry_payload.get("affordances") or []):
            if not isinstance(affordance, dict):
                continue
            if requested_verb and _text(affordance.get("verb")) != requested_verb:
                continue
            if not _entry_supports_affordance(entry_payload, affordance):
                continue
            candidates.append(affordance)

    if not candidates:
        return None, []

    def _candidate_score(candidate: Dict[str, Any]) -> Tuple[int, int, str]:
        required_roles = set(_string_list(candidate.get("required_roles")))
        missing = required_roles - present_roles
        role_match_count = len(required_roles & present_roles)
        complete = 1 if not missing else 0
        return complete, role_match_count, _text(candidate.get("verb"))

    selected = sorted(candidates, key=_candidate_score, reverse=True)[0]
    missing_roles = sorted(set(_string_list(selected.get("required_roles"))) - present_roles)
    return selected, missing_roles

async def _build_object_action_plan(
    *,
    workspace_id: str,
    request: ObjectActionPlanRequest,
    affordance_payload: Dict[str, Any],
    entry_payloads: List[Dict[str, Any]],
) -> Dict[str, Any]:
    planner_backend = _text(affordance_payload.get("planner_backend"))
    role_payloads = [
        {
            "role": entry.role,
            "ref": entry.ref.model_dump(exclude_none=True),
        }
        for entry in request.entries
    ]
    fallback_plan = {
        "instruction": request.instruction,
        "affordance_verb": _text(affordance_payload.get("verb")),
        "role_assignments": role_payloads,
        "write_mode": request.write_mode,
        "meeting_id": request.meeting_id,
        "request_context": dict(request.request_context or {}),
        "planner_backend": planner_backend,
        "object_kinds": [
            {
                "owner_pack": entry_payload.get("owner_pack"),
                "object_kind": entry_payload.get("object_kind"),
            }
            for entry_payload in entry_payloads
        ],
    }
    if not planner_backend:
        return fallback_plan

    result = await _invoke_backend_callable(
        planner_backend,
        workspace_id=workspace_id,
        instruction=request.instruction,
        affordance=affordance_payload,
        role_assignments=role_payloads,
        entries=role_payloads,
        write_mode=request.write_mode,
        meeting_id=request.meeting_id,
        request_context=request.request_context,
    )
    if result is None:
        return fallback_plan
    if not isinstance(result, dict):
        raise ValueError("planner_backend_returned_non_object")
    if isinstance(result.get("plan"), dict):
        return result["plan"]
    return result

def _action_relation_kind_for_role(role: str) -> str:
    if role == "source":
        return "planned_input_for"
    if role == "character":
        return "planned_character_for"
    if role == "evidence":
        return "planned_evidence_for"
    return f"planned_{role}_for"

def _build_object_action_plan_relations(
    *,
    workspace_id: str,
    request: ObjectActionPlanRequest,
    affordance_payload: Dict[str, Any],
    action_plan_id: str,
) -> List[ObjectRelationRecord]:
    targets = [entry for entry in request.entries if entry.role == "target"]
    if not targets:
        return []

    relations: List[ObjectRelationRecord] = []
    for target_entry in targets:
        for role_entry in request.entries:
            if role_entry.role == "target" and role_entry.ref.uri == target_entry.ref.uri:
                continue
            relations.append(
                ObjectRelationRecord(
                    workspace_id=workspace_id,
                    source_ref=role_entry.ref,
                    relation_kind=_action_relation_kind_for_role(role_entry.role),
                    target_ref=target_entry.ref,
                    source_role=role_entry.role,
                    target_role=target_entry.role,
                    provenance_type="object_action_plan",
                    provenance_id=action_plan_id,
                    meeting_id=request.meeting_id,
                    metadata={
                        "action_plan_id": action_plan_id,
                        "command_id": _text((request.request_context or {}).get("command_id")) or None,
                        "affordance_verb": _text(affordance_payload.get("verb")),
                        "write_mode": request.write_mode,
                        "instruction": request.instruction,
                    },
                )
            )
    return relations

def _extract_invoke_plan_payload(request: ObjectActionInvokeRequest) -> Dict[str, Any]:
    plan_payload = dict(request.object_action_plan or {})
    request_plan = plan_payload.get("request_plan")
    if isinstance(request_plan, dict):
        return dict(request_plan)
    return plan_payload

def _extract_invoke_affordance_payload(request: ObjectActionInvokeRequest) -> Dict[str, Any]:
    plan_payload = dict(request.object_action_plan or {})
    selected_affordance = plan_payload.get("selected_affordance")
    return dict(selected_affordance) if isinstance(selected_affordance, dict) else {}

def _extract_invoke_entries(request: ObjectActionInvokeRequest) -> List[ObjectRoleEntry]:
    if request.entries:
        return request.entries
    entries: List[ObjectRoleEntry] = []
    raw_entries = request.object_action_plan.get("role_assignments")
    if not isinstance(raw_entries, list):
        raw_entries = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        try:
            entries.append(ObjectRoleEntry(**raw_entry))
        except Exception:
            logger.debug("Ignoring malformed invoke role assignment", exc_info=True)
    return entries

def _pack_id_from_entries(entries: List[ObjectRoleEntry]) -> str:
    target = next((entry for entry in entries if entry.role == "target"), None)
    if target:
        return target.ref.owner_pack
    if entries:
        return entries[0].ref.owner_pack
    return "object_action"

def _persist_object_action_invocation_task(
    *,
    workspace_id: str,
    execution_id: str,
    request: ObjectActionInvokeRequest,
    entries: List[ObjectRoleEntry],
    executor_result: Dict[str, Any],
    closure: Dict[str, Any] | None,
) -> None:
    now = datetime.now(timezone.utc)
    plan_payload = _extract_invoke_plan_payload(request)
    meeting_id = request.meeting_id or _text(plan_payload.get("meeting_id")) or None
    thread_id = request.thread_id or meeting_id
    action_plan_id = _text(
        request.object_action_plan.get("action_plan_id")
        or plan_payload.get("action_plan_id")
    )
    closure_status = _text((closure or {}).get("status")) or "skipped"
    task_status = TaskStatus.FAILED if closure_status == "failed" else TaskStatus.SUCCEEDED
    normalized_inputs = {
        "instruction": request.instruction,
        "meeting_id": meeting_id,
        "meeting_session_id": meeting_id,
        "thread_id": thread_id,
        "command_id": _text((request.request_context or {}).get("command_id")) or None,
        "object_action_plan": request.object_action_plan,
        "object_action_plan_id": action_plan_id,
        "object_action_entries": [
            entry.model_dump(exclude_none=True) for entry in entries
        ],
        "request_context": dict(request.request_context or {}),
    }
    context = {
        "playbook_code": "object_action_invoke",
        "playbook_name": "Object action invoke",
        "execution_id": execution_id,
        "total_steps": 1,
        "current_step_index": 1,
        "status": closure_status,
        "inputs": normalized_inputs,
        "workspace_id": workspace_id,
        "meeting_session_id": meeting_id,
        "thread_id": thread_id,
        "workflow_result": executor_result,
    }
    if closure:
        context["object_action_closure"] = closure

    store = _get_tasks_store()
    existing = store.get_task_by_execution_id(execution_id)
    if existing:
        merged_context = (
            dict(existing.execution_context)
            if isinstance(existing.execution_context, dict)
            else {}
        )
        merged_context.update(context)
        store.update_task(
            existing.id,
            status=task_status,
            params=normalized_inputs,
            result=executor_result,
            execution_context=merged_context,
            meeting_session_id=meeting_id,
            completed_at=now,
            error=None if task_status == TaskStatus.SUCCEEDED else closure_status,
        )
        return

    store.create_task(
        Task(
            id=execution_id,
            workspace_id=workspace_id,
            message_id=str(uuid.uuid4()),
            execution_id=execution_id,
            pack_id=_pack_id_from_entries(entries),
            task_type="object_action_invocation",
            status=task_status,
            params=normalized_inputs,
            result=executor_result,
            execution_context=context,
            meeting_session_id=meeting_id,
            created_at=now,
            started_at=now,
            completed_at=now,
            error=None if task_status == TaskStatus.SUCCEEDED else closure_status,
        )
    )

def _closure_relation_kind_for_role(role: str) -> str:
    if role == "source":
        return "generated_from_source"
    if role == "character":
        return "generated_with_character"
    if role == "evidence":
        return "generated_from_evidence"
    if role == "baseline":
        return "generated_from_baseline"
    if role == "constraint":
        return "generated_under_constraint"
    if role in {"meeting", "session", "node"}:
        return f"generated_in_{role}"
    return f"generated_from_{role}"

def _build_object_action_closure_relations(
    *,
    workspace_id: str,
    request: ObjectActionClosureRequest,
) -> List[ObjectRelationRecord]:
    relations: List[ObjectRelationRecord] = list(request.output_relations)
    if not request.output_records:
        return relations

    closure_metadata = {
        "action_plan_id": request.action_plan_id,
        "affordance_verb": request.affordance_verb,
        "status": request.status,
        "execution_result": dict(request.execution_result or {}),
    }
    for output_record in request.output_records:
        output_ref = output_record.ref
        for entry in request.entries:
            if entry.role == "output" and entry.ref.uri == output_ref.uri:
                continue
            if entry.role == "target":
                relations.append(
                    ObjectRelationRecord(
                        workspace_id=workspace_id,
                        source_ref=output_ref,
                        relation_kind="landed_in",
                        target_ref=entry.ref,
                        source_role="output",
                        target_role=entry.role,
                        provenance_type="object_action_execution",
                        provenance_id=request.action_plan_id,
                        meeting_id=request.meeting_id,
                        metadata=closure_metadata,
                    )
                )
                continue
            relations.append(
                ObjectRelationRecord(
                    workspace_id=workspace_id,
                    source_ref=entry.ref,
                    relation_kind=_closure_relation_kind_for_role(entry.role),
                    target_ref=output_ref,
                    source_role=entry.role,
                    target_role="output",
                    provenance_type="object_action_execution",
                    provenance_id=request.action_plan_id,
                    meeting_id=request.meeting_id,
                    metadata=closure_metadata,
                )
            )
    return relations


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
