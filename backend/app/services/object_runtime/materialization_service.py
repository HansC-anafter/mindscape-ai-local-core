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
from backend.app.services.object_runtime.meeting_projection import *

def _select_materializer_backend(
    entry_payload: Dict[str, Any],
    *,
    verb: str,
    write_mode: str,
) -> str | None:
    candidates = list(entry_payload.get("materializer_backends") or [])

    for materializer in candidates:
        verbs = list(materializer.get("verbs") or [])
        candidate_write_mode = _text(materializer.get("write_mode"))
        backend = _text(materializer.get("backend"))
        if (
            backend
            and verb in verbs
            and candidate_write_mode
            and candidate_write_mode == write_mode
        ):
            return backend

    for materializer in candidates:
        verbs = list(materializer.get("verbs") or [])
        backend = _text(materializer.get("backend"))
        if backend and verb in verbs:
            return backend

    return None

async def _execute_materializer_backend(
    *,
    workspace_id: str,
    object_ref: ObjectRef,
    entry_payload: Dict[str, Any],
    meeting_id: str | None,
    verb: str,
    write_mode: str,
    source_objects: List[Dict[str, Any]],
    context_objects: List[Dict[str, Any]],
    intent_summary: str,
    request_context: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    backend_path = _select_materializer_backend(
        entry_payload,
        verb=verb,
        write_mode=write_mode,
    )
    if not backend_path:
        return None

    return await _invoke_backend_callable(
        backend_path,
        workspace_id=workspace_id,
        object_id=object_ref.object_id,
        meeting_id=meeting_id,
        verb=verb,
        write_mode=write_mode,
        source_objects=source_objects,
        context_objects=context_objects,
        intent_summary=intent_summary,
        request_context=dict(request_context or {}),
    )

def _normalize_materializer_outcome(
    *,
    result: Dict[str, Any],
    workspace_id: str,
    allowed_statuses: set[str],
    default_status: str,
) -> Tuple[
    str,
    List[ObjectRef],
    List[str],
    List[str],
    Dict[str, Any] | None,
    List[SelectionResolveError],
]:
    staged_refs: List[ObjectRef] = []
    raw_staged_ref = result.get("staged_ref")
    if isinstance(raw_staged_ref, dict):
        staged_refs.append(
            _coerce_materialized_ref_payload(raw_staged_ref, workspace_id=workspace_id)
        )
    for raw_staged in list(result.get("staged_refs") or []):
        if isinstance(raw_staged, dict):
            staged_refs.append(
                _coerce_materialized_ref_payload(raw_staged, workspace_id=workspace_id)
            )

    review_routes = _coerce_route_list(
        result,
        single_key="review_route",
        plural_key="review_routes",
    )
    canonical_routes = _coerce_route_list(
        result,
        single_key="canonical_route",
        plural_key="canonical_routes",
    )
    canonical_storyboard_route = _text(result.get("canonical_storyboard_route"))
    if canonical_storyboard_route and canonical_storyboard_route not in canonical_routes:
        canonical_routes.append(canonical_storyboard_route)

    request_plan = _coerce_request_plan(result)
    errors = _coerce_materializer_errors(result)
    normalized_status = _text(result.get("status"))
    if normalized_status not in allowed_statuses:
        if request_plan or review_routes or canonical_routes:
            normalized_status = "planned" if "planned" in allowed_statuses else default_status
        elif staged_refs:
            normalized_status = "materialized" if "materialized" in allowed_statuses else default_status
        elif errors:
            normalized_status = "rejected" if "rejected" in allowed_statuses else default_status
        else:
            normalized_status = default_status

    if errors and normalized_status not in {"rejected", "planned"}:
        normalized_status = "rejected" if "rejected" in allowed_statuses else default_status

    return (
        normalized_status,
        staged_refs,
        review_routes,
        canonical_routes,
        request_plan,
        errors,
    )

async def _materialize_target_outcome(
    *,
    workspace_id: str,
    meeting_id: str,
    request: ObjectMeetingAttachRequest,
    target_ref: ObjectRef,
    target_entry_payload: Dict[str, Any],
    context_records: List[ObjectMeetingContextRecord],
) -> Tuple[str, List[ObjectRef], List[str], List[SelectionResolveError], Dict[str, Any] | None]:
    try:
        result = await _execute_materializer_backend(
            workspace_id=workspace_id,
            object_ref=target_ref,
            entry_payload=target_entry_payload,
            meeting_id=meeting_id,
            verb="attach",
            write_mode=request.write_mode,
            source_objects=_build_materializer_context_objects(
                context_records,
                roles={"source"},
            ),
            context_objects=_build_materializer_context_objects(context_records),
            intent_summary=request.intent_summary,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer materializer failed for %s.%s",
            target_ref.owner_pack,
            target_ref.object_kind,
        )
        return (
            "rejected",
            [],
            [],
            [
                SelectionResolveError(
                    code="materializer_failed",
                    message=(
                        "Owner-pack materializer failed while staging the attach outcome: "
                        f"{exc}"
                    ),
                )
            ],
            None,
        )
    if result is None:
        return "attached", [], [], [], None

    if not isinstance(result, dict):
        return (
            "rejected",
            [],
            [],
            [
                SelectionResolveError(
                    code="invalid_materializer_result",
                    message="Owner-pack materializer returned a non-object payload.",
                )
            ],
            None,
        )

    try:
        (
            normalized_status,
            staged_refs,
            review_routes,
            _canonical_routes,
            _request_plan,
            errors,
        ) = _normalize_materializer_outcome(
            result=result,
            workspace_id=workspace_id,
            allowed_statuses={"attached", "materialized", "rejected"},
            default_status="attached",
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer materializer normalization failed for %s.%s",
            target_ref.owner_pack,
            target_ref.object_kind,
        )
        return (
            "rejected",
            [],
            [],
            [
                SelectionResolveError(
                    code="materializer_failed",
                    message=(
                        "Owner-pack materializer failed while staging the attach outcome: "
                        f"{exc}"
                    ),
                )
            ],
            None,
        )

    return normalized_status, staged_refs, review_routes, errors, result

async def materialize_object_outcome(
    request: ObjectMaterializeRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectMaterializeResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    entry, _summary = await _resolve_attach_ref(
        registry=registry,
        workspace_id=workspace_id,
        ref=request.object_ref,
        require_meeting_projection=False,
        error_code="object_not_found",
    )
    entry_payload = registry.get_entry(
        request.object_ref.owner_pack,
        request.object_ref.object_kind,
    ) or {}
    if not _select_materializer_backend(
        entry_payload,
        verb=request.verb,
        write_mode=request.write_mode,
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "materializer_unavailable",
                "message": "Materialization is unavailable for this object kind and verb.",
                "details": {
                    "owner_pack": request.object_ref.owner_pack,
                    "object_kind": request.object_ref.object_kind,
                    "verb": request.verb,
                    "write_mode": request.write_mode,
                },
            },
        )

    context_records: List[ObjectMeetingContextRecord] = []
    for context_entry in request.context_entries:
        context_ref = context_entry.ref
        _context_entry, context_summary = await _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=context_ref,
            require_meeting_projection=False,
            error_code="object_not_found",
        )
        context_entry_payload = registry.get_entry(
            context_ref.owner_pack,
            context_ref.object_kind,
        ) or {}
        meeting_projection = None
        if _context_entry.meeting_projection_capabilities.available:
            meeting_projection = await _resolve_meeting_projection_payload(
                entry_payload=context_entry_payload,
                workspace_id=workspace_id,
                ref=context_ref,
                summary=context_summary,
                verb=request.verb,
            )
        context_records.append(
            ObjectMeetingContextRecord(
                role=context_entry.role,
                ref=context_ref,
                summary=context_summary,
                meeting_projection=meeting_projection,
            )
        )

    try:
        result = await _execute_materializer_backend(
            workspace_id=workspace_id,
            object_ref=request.object_ref,
            entry_payload=entry_payload,
            meeting_id=request.meeting_id,
            verb=request.verb,
            write_mode=request.write_mode,
            source_objects=_build_materializer_context_objects(
                context_records,
                roles={"source"},
            ),
            context_objects=_build_materializer_context_objects(context_records),
            intent_summary=request.intent_summary,
            request_context=request.request_context,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer materializer failed for %s.%s",
            request.object_ref.owner_pack,
            request.object_ref.object_kind,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "materializer_failed",
                "message": "Owner-pack materializer failed while planning the requested outcome.",
                "details": {
                    "owner_pack": request.object_ref.owner_pack,
                    "object_kind": request.object_ref.object_kind,
                    "verb": request.verb,
                    "error": str(exc),
                },
            },
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_materializer_result",
                "message": "Owner-pack materializer returned a non-object payload.",
                "details": {
                    "owner_pack": request.object_ref.owner_pack,
                    "object_kind": request.object_ref.object_kind,
                    "verb": request.verb,
                },
            },
        )

    (
        response_status,
        staged_refs,
        review_routes,
        canonical_routes,
        request_plan,
        response_errors,
    ) = _normalize_materializer_outcome(
        result=result,
        workspace_id=workspace_id,
        allowed_statuses={"planned", "materialized", "rejected"},
        default_status="planned",
    )

    return ObjectMaterializeResponse(
        workspace_id=workspace_id,
        status=response_status,
        verb=request.verb,
        object_ref=request.object_ref,
        staged_refs=staged_refs,
        review_routes=review_routes,
        canonical_routes=canonical_routes,
        request_plan=request_plan,
        errors=response_errors,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
