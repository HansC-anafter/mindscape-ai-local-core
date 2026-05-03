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
from backend.app.services.object_runtime.summary_service import *

def _attach_action() -> ObjectAction:
    return ObjectAction(
        action_code="attach_to_meeting",
        label="Bring Into Meeting",
        description="Attach this object to a meeting as a source or target.",
        verb="attach",
        mode="meeting",
        requires_review=False,
        target_kind=None,
    )

def _recommend_action() -> ObjectAction:
    return ObjectAction(
        action_code="recommend_related_objects",
        label="Recommend Related Objects",
        description="Suggest nearby refs, storyboard targets, or review pathways.",
        verb="recommend",
        mode="contextual",
        requires_review=False,
        target_kind=None,
    )

def _open_owner_surface_action() -> ObjectAction:
    return ObjectAction(
        action_code="open_owner_surface",
        label="Open Owner Surface",
        description="Open the owner pack surface for this object.",
        verb="open",
        mode="navigation",
        requires_review=False,
        target_kind=None,
    )

def _build_actions(
    *,
    entry: ObjectCatalogEntry,
    request: SelectionResolveRequest,
) -> Tuple[List[ObjectAction], List[SelectionResolveError]]:
    if request.mode == "resolve_only":
        return [], []

    meeting_verbs = set(entry.meeting_projection_capabilities.verbs)
    actions: List[ObjectAction] = []
    warnings: List[SelectionResolveError] = []

    if request.mode in {"contextual_actions", "attach_to_meeting"}:
        if "attach" in meeting_verbs:
            actions.append(_attach_action())
        elif request.mode == "attach_to_meeting":
            warnings.append(
                SelectionResolveError(
                    code="meeting_attach_not_supported",
                    message=(
                        "Resolved object does not declare attach support for meeting entry."
                    ),
                )
            )

    if request.mode == "contextual_actions" and "recommend" in meeting_verbs:
        actions.append(_recommend_action())

    if request.mode in {"contextual_actions", "open_owner_surface"}:
        if request.surface.route:
            actions.append(_open_owner_surface_action())
        elif request.mode == "open_owner_surface":
            warnings.append(
                SelectionResolveError(
                    code="owner_surface_missing",
                    message="Selection surface did not provide an owner route.",
                )
            )

    return actions, warnings

def _validate_selection_hints(request: SelectionResolveRequest) -> None:
    if not request.hints:
        return

    identity_values = [
        request.hints.owner_pack,
        request.hints.object_kind,
        request.hints.object_id,
    ]
    populated_count = sum(1 for value in identity_values if value)
    if 0 < populated_count < 3:
        raise HTTPException(
            status_code=422,
            detail=(
                "Selection hints must provide owner_pack, object_kind, and object_id "
                "together when any object identity hint is supplied."
            ),
        )

    if (
        request.surface.surface_type == "installed_pack_ui"
        and request.surface.pack_code
        and request.hints.owner_pack
        and request.surface.pack_code != request.hints.owner_pack
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "surface.pack_code and hints.owner_pack must match for installed "
                "pack UI selections."
            ),
        )

async def resolve_workspace_selection(
    request: SelectionResolveRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> SelectionResolveResponse:
    await _ensure_workspace_exists(workspace_id)
    _validate_selection_hints(request)

    if not request.hints or not (
        request.hints.owner_pack
        and request.hints.object_kind
        and request.hints.object_id
    ):
        return SelectionResolveResponse(
            workspace_id=workspace_id,
            selection_id=request.selection_id,
            status="unresolved",
            errors=[
                SelectionResolveError(
                    code="insufficient_hints",
                    message=(
                        "Selection did not provide enough addressable object hints "
                        "to resolve an ObjectRef."
                    ),
                )
            ],
        )

    registry = _get_object_catalog_registry()
    entry_payload = registry.get_entry(
        request.hints.owner_pack,
        request.hints.object_kind,
    )
    if not entry_payload:
        return SelectionResolveResponse(
            workspace_id=workspace_id,
            selection_id=request.selection_id,
            status="unresolved",
            errors=[
                SelectionResolveError(
                    code="object_not_found",
                    message=(
                        "No addressable object could be resolved from the supplied "
                        "selection hints."
                    ),
                )
            ],
        )

    entry = _to_catalog_entry(entry_payload)
    ref = _build_object_ref(
        workspace_id=workspace_id,
        owner_pack=request.hints.owner_pack,
        object_kind=request.hints.object_kind,
        object_id=request.hints.object_id,
        version=request.hints.version,
        selector=request.hints.selector,
        source_surface=request.hints.source_surface or request.surface.surface_id,
    )
    fallback_summary = _build_object_summary(entry=entry, ref=ref, request=request)
    summary = await _resolve_runtime_summary(
        entry_payload=entry_payload,
        workspace_id=workspace_id,
        ref=ref,
        fallback_summary=fallback_summary,
    )
    actions, warnings = _build_actions(entry=entry, request=request)

    return SelectionResolveResponse(
        workspace_id=workspace_id,
        selection_id=request.selection_id,
        status="resolved",
        resolved_objects=[
            ResolvedSelectionObject(ref=ref, summary=summary, actions=actions)
        ],
        errors=warnings,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
