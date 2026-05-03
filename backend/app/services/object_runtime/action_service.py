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

from backend.app.services.object_runtime.action_helpers import *
from backend.app.services.object_runtime.common import *
from backend.app.services.object_runtime.dependencies import *

async def plan_workspace_object_action(
    request: ObjectActionPlanRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectActionPlanResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()

    entry_payloads: List[Dict[str, Any]] = []
    for role_entry in request.entries:
        _validate_object_ref_identity(role_entry.ref, workspace_id)
        entry_payload = registry.get_entry(
            role_entry.ref.owner_pack,
            role_entry.ref.object_kind,
        )
        if not entry_payload:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "object_kind_not_declared",
                    "message": "ObjectRef does not map to an installed addressable object kind.",
                    "details": {
                        "owner_pack": role_entry.ref.owner_pack,
                        "object_kind": role_entry.ref.object_kind,
                        "object_id": role_entry.ref.object_id,
                    },
                },
            )
        entry_payloads.append(entry_payload)

    selected_affordance, missing_roles = _select_action_affordance(
        entry_payloads,
        requested_verb=request.affordance_verb,
        present_roles={entry.role for entry in request.entries},
    )
    if selected_affordance is None:
        return ObjectActionPlanResponse(
            workspace_id=workspace_id,
            status="unsupported",
            role_assignments=request.entries,
            write_mode=request.write_mode,
            errors=[
                SelectionResolveError(
                    code="affordance_unavailable",
                    message="No installed object affordance matches the requested object roles.",
                )
            ],
        )

    normalized_affordance = ObjectAffordanceCapability(**selected_affordance)
    if missing_roles:
        return ObjectActionPlanResponse(
            workspace_id=workspace_id,
            status="needs_disambiguation",
            selected_affordance=normalized_affordance,
            role_assignments=request.entries,
            missing_roles=missing_roles,
            write_mode=request.write_mode,
            errors=[
                SelectionResolveError(
                    code="missing_required_roles",
                    message="The selected affordance requires additional object roles.",
                )
            ],
        )

    try:
        plan = await _build_object_action_plan(
            workspace_id=workspace_id,
            request=request,
            affordance_payload=selected_affordance,
            entry_payloads=entry_payloads,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer affordance planner failed for workspace %s",
            workspace_id,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "planner_backend_failed",
                "message": "Owner-pack affordance planner failed.",
                "details": {
                    "affordance_verb": selected_affordance.get("verb"),
                    "error": str(exc),
                },
            },
        ) from exc

    action_plan_id = _text(plan.get("action_plan_id")) or f"oap_{uuid.uuid4().hex}"
    plan = {
        **plan,
        "action_plan_id": action_plan_id,
    }
    relation_records = _build_object_action_plan_relations(
        workspace_id=workspace_id,
        request=request,
        affordance_payload=selected_affordance,
        action_plan_id=action_plan_id,
    )
    if relation_records:
        try:
            _get_object_relation_registry_store().upsert_many(
                workspace_id,
                relation_records,
            )
        except Exception:
            logger.exception(
                "Addressable Object Layer failed to persist action plan relations for workspace %s",
                workspace_id,
            )

    return ObjectActionPlanResponse(
        workspace_id=workspace_id,
        status="planned",
        selected_affordance=normalized_affordance,
        role_assignments=request.entries,
        write_mode=request.write_mode,
        request_plan=plan,
    )


async def invoke_workspace_object_action(
    request: ObjectActionInvokeRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectActionInvokeResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    entries = _extract_invoke_entries(request)
    plan_payload = _extract_invoke_plan_payload(request)
    affordance_payload = _extract_invoke_affordance_payload(request)
    action_plan_id = _text(
        request.object_action_plan.get("action_plan_id")
        or plan_payload.get("action_plan_id")
    )
    if not action_plan_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "action_plan_id_required",
                "message": "object_action_plan.request_plan.action_plan_id is required for invocation.",
            },
        )
    if not entries:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "role_assignments_required",
                "message": "Invocation requires role assignments from the planned object action.",
            },
        )

    for role_entry in entries:
        _validate_catalog_object_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=role_entry.ref,
        )

    if not affordance_payload:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "selected_affordance_required",
                "message": "Invocation requires selected_affordance from the plan response.",
            },
        )
    affordance = ObjectAffordanceCapability(**affordance_payload)
    executor_backend = _text(affordance.executor_backend)
    if not executor_backend:
        return ObjectActionInvokeResponse(
            workspace_id=workspace_id,
            status="failed",
            action_plan_id=action_plan_id,
            execution_id=request.execution_id or f"oai_{uuid.uuid4().hex}",
            task_id=request.execution_id or action_plan_id,
            errors=[
                SelectionResolveError(
                    code="executor_backend_missing",
                    message="Selected affordance does not declare an executor backend.",
                )
            ],
        )

    execution_id = request.execution_id or f"oai_{uuid.uuid4().hex}"
    role_payloads = [
        {
            "role": entry.role,
            "ref": entry.ref.model_dump(exclude_none=True),
        }
        for entry in entries
    ]
    meeting_id = request.meeting_id or _text(plan_payload.get("meeting_id")) or None
    request_context = {
        **dict(plan_payload.get("request_context") or {}),
        **dict(request.request_context or {}),
    }
    executor_result_raw = await _invoke_backend_callable(
        executor_backend,
        workspace_id=workspace_id,
        instruction=request.instruction,
        affordance=affordance.model_dump(exclude_none=True),
        role_assignments=role_payloads,
        entries=role_payloads,
        write_mode=request.object_action_plan.get("write_mode")
        or plan_payload.get("write_mode"),
        meeting_id=meeting_id,
        thread_id=request.thread_id or meeting_id,
        request_context=request_context,
        request_plan=plan_payload,
        action_plan_id=action_plan_id,
        execution_id=execution_id,
    )
    executor_result = (
        dict(executor_result_raw)
        if isinstance(executor_result_raw, dict)
        else {"result": executor_result_raw}
    )
    normalized_inputs = {
        "instruction": request.instruction,
        "meeting_id": meeting_id,
        "meeting_session_id": meeting_id,
        "thread_id": request.thread_id or meeting_id,
        "command_id": _text(request_context.get("command_id")) or None,
        "object_action_plan": request.object_action_plan,
        "object_action_plan_id": action_plan_id,
        "object_action_entries": role_payloads,
        "request_context": request_context,
    }
    from backend.app.services.object_action_closure_wiring import (
        close_object_action_from_execution_result,
    )

    closure = close_object_action_from_execution_result(
        workspace_id=workspace_id,
        execution_id=execution_id,
        inputs=normalized_inputs,
        execution_result=executor_result,
    )
    _persist_object_action_invocation_task(
        workspace_id=workspace_id,
        execution_id=execution_id,
        request=request,
        entries=entries,
        executor_result=executor_result,
        closure=closure,
    )
    closure_status = _text((closure or {}).get("status")) or "skipped"
    if closure_status not in {"succeeded", "failed", "skipped"}:
        closure_status = "succeeded"
    return ObjectActionInvokeResponse(
        workspace_id=workspace_id,
        status=closure_status,  # type: ignore[arg-type]
        action_plan_id=action_plan_id,
        execution_id=execution_id,
        task_id=execution_id,
        closure=closure,
        executor_result=executor_result,
    )


async def close_workspace_object_action(
    request: ObjectActionClosureRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectActionClosureResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()

    for role_entry in request.entries:
        _validate_catalog_object_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=role_entry.ref,
        )

    for output_record in request.output_records:
        _validate_catalog_object_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=output_record.ref,
        )

    for relation in request.output_relations:
        _validate_catalog_object_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=relation.source_ref,
        )
        _validate_catalog_object_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=relation.target_ref,
        )

    indexed_output_count = _get_object_instance_registry_store().upsert_many(
        workspace_id,
        request.output_records,
    )
    relation_records = _build_object_action_closure_relations(
        workspace_id=workspace_id,
        request=request,
    )
    indexed_relation_count = _get_object_relation_registry_store().upsert_many(
        workspace_id,
        relation_records,
    )

    return ObjectActionClosureResponse(
        workspace_id=workspace_id,
        action_plan_id=request.action_plan_id,
        status=request.status,
        indexed_output_count=indexed_output_count,
        indexed_relation_count=indexed_relation_count,
        output_refs=[record.ref for record in request.output_records],
        relations=relation_records,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
