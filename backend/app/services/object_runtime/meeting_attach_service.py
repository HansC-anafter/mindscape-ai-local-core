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
from backend.app.services.object_runtime.materialization_service import *
from backend.app.services.object_runtime.meeting_projection import *

def _build_session_attachment_metadata(
    *,
    request: ObjectMeetingAttachRequest,
    handoff_payload: dict,
    response_status: str,
    staged_refs: List[ObjectRef],
    review_routes: List[str],
    materialization_result: Dict[str, Any] | None,
) -> dict:
    safe_handoff_payload = jsonable_encoder(handoff_payload)
    safe_materialization_result = (
        jsonable_encoder(materialization_result)
        if materialization_result is not None
        else None
    )
    return {
        "meeting_type": request.meeting_type,
        "intent_summary": request.intent_summary,
        "status": response_status,
        "write_mode": request.write_mode,
        "context_entries": [
            {
                "role": entry.role,
                "ref": entry.ref.model_dump(exclude_none=True),
            }
            for entry in request.entries
        ],
        "target_ref": (
            request.target_ref.model_dump(exclude_none=True)
            if request.target_ref
            else None
        ),
        "staged_refs": [ref.model_dump(exclude_none=True) for ref in staged_refs],
        "review_routes": list(review_routes),
        "materialization_result": safe_materialization_result,
        "handoff_in": safe_handoff_payload,
        "context_attachments": safe_handoff_payload.get("context_attachments") or [],
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

def _upsert_meeting_session_metadata(session: MeetingSession, attachment_metadata: dict) -> None:
    session.metadata = dict(session.metadata or {})
    session.metadata["addressable_object_layer"] = attachment_metadata

async def attach_objects_to_meeting(
    request: ObjectMeetingAttachRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectMeetingAttachResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()

    target_entries = [entry for entry in request.entries if entry.role == "target"]
    if len(target_entries) > 1:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "multiple_targets_not_supported",
                "message": "Attach requests currently support at most one target object.",
            },
        )
    has_non_target_context = any(entry.role != "target" for entry in request.entries)

    context_records: List[ObjectMeetingContextRecord] = []
    for request_entry in request.entries:
        ref = request_entry.ref
        require_meeting_projection = request_entry.role != "target"
        catalog_entry, summary = await _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=ref,
            require_meeting_projection=require_meeting_projection,
            error_code=(
                "target_ref_invalid"
                if request_entry.role == "target"
                else "object_not_found"
            ),
        )
        entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind) or {}
        meeting_projection = None
        if catalog_entry.meeting_projection_capabilities.available:
            meeting_projection = await _resolve_meeting_projection_payload(
                entry_payload=entry_payload,
                workspace_id=workspace_id,
                ref=ref,
                summary=summary,
                verb="attach",
            )
        context_records.append(
            ObjectMeetingContextRecord(
                role=request_entry.role,
                ref=ref,
                summary=summary,
                meeting_projection=meeting_projection,
            )
        )

    target_ref = target_entries[0].ref if target_entries else None

    session_store = _get_meeting_session_store()
    if request.meeting_id:
        session = session_store.get_by_id(request.meeting_id)
        if not session or session.workspace_id != workspace_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "meeting_not_found",
                    "message": "Meeting session was not found for this workspace.",
                    "details": {"meeting_id": request.meeting_id},
                },
            )
        if not session.is_active:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "meeting_closed",
                    "message": "Meeting session is no longer active.",
                    "details": {"meeting_id": request.meeting_id},
                },
            )
    else:
        session = MeetingSession.new(
            workspace_id=workspace_id,
            meeting_type=request.meeting_type,
            agenda=[request.intent_summary],
        )
        session.start()
        session_store.create(session)

    attachment_service = _get_object_meeting_attachment_service()
    handoff_result = attachment_service.build_handoff(
        workspace_id=workspace_id,
        meeting_id=session.id,
        meeting_type=request.meeting_type,
        intent_summary=request.intent_summary,
        write_mode=request.write_mode,
        context_objects=context_records,
    )
    response_status = "attached"
    staged_refs: List[ObjectRef] = []
    review_routes: List[str] = []
    response_errors: List[SelectionResolveError] = []
    materialization_result: Dict[str, Any] | None = None

    if target_ref and has_non_target_context:
        target_entry_payload = registry.get_entry(
            target_ref.owner_pack,
            target_ref.object_kind,
        )
        if target_entry_payload:
            (
                response_status,
                staged_refs,
                review_routes,
                response_errors,
                materialization_result,
            ) = await _materialize_target_outcome(
                workspace_id=workspace_id,
                meeting_id=session.id,
                request=request,
                target_ref=target_ref,
                target_entry_payload=target_entry_payload,
                context_records=context_records,
            )

    _upsert_meeting_session_metadata(
        session,
        _build_session_attachment_metadata(
            request=request,
            handoff_payload=handoff_result.handoff_in.model_dump(exclude_none=True),
            response_status=response_status,
            staged_refs=staged_refs,
            review_routes=review_routes,
            materialization_result=materialization_result,
        ),
    )
    session_store.update(session)

    attachment_summaries = [
        MeetingAttachmentSummary(
            role=record.role,
            ref=record.ref,
            projection_level="meeting",
        )
        for record in context_records
    ]

    return ObjectMeetingAttachResponse(
        workspace_id=workspace_id,
        meeting_id=session.id,
        status=response_status,
        attachments=attachment_summaries,
        target_ref=target_ref,
        staged_refs=staged_refs,
        review_routes=review_routes,
        errors=response_errors,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
