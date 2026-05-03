"""Workspace-scoped runtime API facade for the Addressable Object Layer."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Path as PathParam, Query

from backend.app.models.object_runtime import (
    ObjectActionClosureRequest,
    ObjectActionClosureResponse,
    ObjectActionInvokeRequest,
    ObjectActionInvokeResponse,
    ObjectActionPlanRequest,
    ObjectActionPlanResponse,
    ObjectCatalogResponse,
    ObjectGraphProjectRequest,
    ObjectGraphProjectResponse,
    ObjectInstanceIndexRequest,
    ObjectInstanceIndexResponse,
    ObjectInstanceSyncRequest,
    ObjectInstanceSyncResponse,
    ObjectMaterializeRequest,
    ObjectMaterializeResponse,
    ObjectMeetingAttachRequest,
    ObjectMeetingAttachResponse,
    ObjectMentionCompletionResponse,
    ObjectReadRequest,
    ObjectReadResponse,
    ObjectRelationIndexRequest,
    ObjectRelationIndexResponse,
    ObjectRelationSearchResponse,
    ObjectSearchResponse,
    SelectionResolveError,
    SelectionResolveRequest,
    SelectionResolveResponse,
)
from backend.app.services.object_runtime import route_services as _services

router = APIRouter()

_SYNC_NAMES = [
    "_resolve_local_core_root",
    "_get_object_catalog_registry",
    "_get_workspace_store",
    "_get_meeting_session_store",
    "_get_object_meeting_attachment_service",
    "_get_object_instance_registry_store",
    "_get_object_relation_registry_store",
    "_get_tasks_store",
    "_ensure_workspace_exists",
    "_to_catalog_entry",
    "_text",
    "_string_list",
    "_build_object_ref",
    "_parse_mindscape_uri",
    "_build_object_summary",
    "_build_catalog_summary",
    "_default_mention_token",
    "_score_mention_record",
    "_to_mention_completion_item",
    "_entry_supports_affordance",
    "_select_action_affordance",
    "_build_object_action_plan",
    "_action_relation_kind_for_role",
    "_build_object_action_plan_relations",
    "_extract_invoke_plan_payload",
    "_extract_invoke_affordance_payload",
    "_extract_invoke_entries",
    "_pack_id_from_entries",
    "_persist_object_action_invocation_task",
    "_closure_relation_kind_for_role",
    "_build_object_action_closure_relations",
    "_relation_record_to_graph_relation",
    "_first_text",
    "_coerce_summary_from_backend_payload",
    "_select_summary_backend",
    "_resolve_runtime_summary",
    "_default_meeting_projection_payload",
    "_attach_action",
    "_recommend_action",
    "_open_owner_surface_action",
    "_build_actions",
    "_validate_selection_hints",
    "_validate_object_ref_identity",
    "_split_object_uri",
    "_coerce_read_object_ref",
    "_validate_catalog_object_ref",
    "_resolve_attach_ref",
    "_select_materializer_backend",
    "_select_meeting_projection_backend",
    "_select_graph_projection_backend",
    "_invoke_backend_callable",
    "_build_materializer_context_objects",
    "_resolve_meeting_projection_payload",
    "_coerce_materialized_ref_payload",
    "_coerce_materializer_errors",
    "_coerce_route_list",
    "_coerce_request_plan",
    "_execute_materializer_backend",
    "_normalize_materializer_outcome",
    "_materialize_target_outcome",
    "_build_session_attachment_metadata",
    "_upsert_meeting_session_metadata",
    "_coerce_relation_target_ref",
    "_normalize_graph_relations",
    "_coerce_guidance_ref",
    "_normalize_guidance_cards",
    "_resolve_graph_projection",
    "get_object_index_sync_service",
    "get_object_index_sync_status",
]

for _name in _SYNC_NAMES:
    globals()[_name] = getattr(_services, _name)


def _sync_service_globals() -> None:
    for name in _SYNC_NAMES:
        setattr(_services, name, globals()[name])


@router.get(
    "/{workspace_id}/object-catalog",
    response_model=ObjectCatalogResponse,
    response_model_exclude={
        "entries": {
            "__all__": {
                "affordances",
                "granularity",
                "indexer_backend",
                "mention_fields",
                "owner_surface_patterns",
                "selector_families",
            }
        }
    },
)
async def get_workspace_object_catalog(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    owner_pack: str | None = Query(None, description="Filter by owner pack"),
    object_kind: str | None = Query(None, description="Filter by object kind"),
    supports: str | None = Query(None, description="Filter by declared support flag"),
    include_examples: bool = Query(
        False,
        description="Reserved for future example object refs when available.",
    ),
) -> ObjectCatalogResponse:
    _sync_service_globals()
    return await _services.get_workspace_object_catalog(
        workspace_id=workspace_id,
        owner_pack=owner_pack,
        object_kind=object_kind,
        supports=supports,
        include_examples=include_examples,
    )


@router.post(
    "/{workspace_id}/objects/index",
    response_model=ObjectInstanceIndexResponse,
)
async def index_workspace_objects(
    request: ObjectInstanceIndexRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectInstanceIndexResponse:
    _sync_service_globals()
    return await _services.index_workspace_objects(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/objects/sync",
    response_model=ObjectInstanceSyncResponse,
)
async def sync_workspace_object_index(
    request: ObjectInstanceSyncRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectInstanceSyncResponse:
    _sync_service_globals()
    return await _services.sync_workspace_object_index(request=request, workspace_id=workspace_id)


@router.get("/{workspace_id}/objects/sync/status")
async def get_workspace_object_index_sync_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> Dict[str, Any]:
    _sync_service_globals()
    return await _services.get_workspace_object_index_sync_status(workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/objects/relations/index",
    response_model=ObjectRelationIndexResponse,
)
async def index_workspace_object_relations(
    request: ObjectRelationIndexRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectRelationIndexResponse:
    _sync_service_globals()
    return await _services.index_workspace_object_relations(
        request=request,
        workspace_id=workspace_id,
    )


@router.get(
    "/{workspace_id}/objects/relations",
    response_model=ObjectRelationSearchResponse,
)
async def search_workspace_object_relations(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    object_uri: str | None = Query(None, description="Find inbound or outbound edges for this object URI"),
    source_uri: str | None = Query(None, description="Filter by source object URI"),
    target_uri: str | None = Query(None, description="Filter by target object URI"),
    relation_kind: str | None = Query(None, description="Filter by relation kind"),
    meeting_id: str | None = Query(None, description="Filter by meeting/session provenance"),
    limit: int = Query(100, ge=1, le=500, description="Maximum result count"),
) -> ObjectRelationSearchResponse:
    _sync_service_globals()
    return await _services.search_workspace_object_relations(
        workspace_id=workspace_id,
        object_uri=object_uri,
        source_uri=source_uri,
        target_uri=target_uri,
        relation_kind=relation_kind,
        meeting_id=meeting_id,
        limit=limit,
    )


@router.get(
    "/{workspace_id}/objects/search",
    response_model=ObjectSearchResponse,
)
async def search_workspace_objects(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    query: str = Query("", description="Search text or mention fragment"),
    owner_pack: str | None = Query(None, description="Filter by owner pack"),
    object_kind: str | None = Query(None, description="Filter by object kind"),
    limit: int = Query(20, ge=1, le=100, description="Maximum result count"),
) -> ObjectSearchResponse:
    _sync_service_globals()
    return await _services.search_workspace_objects(
        workspace_id=workspace_id,
        query=query,
        owner_pack=owner_pack,
        object_kind=object_kind,
        limit=limit,
    )


@router.post(
    "/{workspace_id}/objects/read",
    response_model=ObjectReadResponse,
)
async def read_workspace_object(
    request: ObjectReadRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectReadResponse:
    _sync_service_globals()
    return await _services.read_workspace_object(request=request, workspace_id=workspace_id)


@router.get(
    "/{workspace_id}/objects/complete",
    response_model=ObjectMentionCompletionResponse,
)
async def complete_workspace_objects(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    query: str = Query("", description="Mention query without the leading @"),
    owner_pack: str | None = Query(None, description="Filter by owner pack"),
    object_kind: str | None = Query(None, description="Filter by object kind"),
    limit: int = Query(20, ge=1, le=50, description="Maximum result count"),
) -> ObjectMentionCompletionResponse:
    _sync_service_globals()
    return await _services.complete_workspace_objects(
        workspace_id=workspace_id,
        query=query,
        owner_pack=owner_pack,
        object_kind=object_kind,
        limit=limit,
    )


@router.post(
    "/{workspace_id}/object-actions/plan",
    response_model=ObjectActionPlanResponse,
)
async def plan_workspace_object_action(
    request: ObjectActionPlanRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectActionPlanResponse:
    _sync_service_globals()
    return await _services.plan_workspace_object_action(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/object-actions/invoke",
    response_model=ObjectActionInvokeResponse,
)
async def invoke_workspace_object_action(
    request: ObjectActionInvokeRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectActionInvokeResponse:
    _sync_service_globals()
    return await _services.invoke_workspace_object_action(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/object-actions/close",
    response_model=ObjectActionClosureResponse,
)
async def close_workspace_object_action(
    request: ObjectActionClosureRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectActionClosureResponse:
    _sync_service_globals()
    return await _services.close_workspace_object_action(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/selection/resolve",
    response_model=SelectionResolveResponse,
)
async def resolve_workspace_selection(
    request: SelectionResolveRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> SelectionResolveResponse:
    _sync_service_globals()
    return await _services.resolve_workspace_selection(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/object-meeting-attach",
    response_model=ObjectMeetingAttachResponse,
)
async def attach_objects_to_meeting(
    request: ObjectMeetingAttachRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectMeetingAttachResponse:
    _sync_service_globals()
    return await _services.attach_objects_to_meeting(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/object-materialize",
    response_model=ObjectMaterializeResponse,
)
async def materialize_object_outcome(
    request: ObjectMaterializeRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectMaterializeResponse:
    _sync_service_globals()
    return await _services.materialize_object_outcome(request=request, workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/object-graph/project",
    response_model=ObjectGraphProjectResponse,
)
async def project_object_graph(
    request: ObjectGraphProjectRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectGraphProjectResponse:
    _sync_service_globals()
    return await _services.project_object_graph(request=request, workspace_id=workspace_id)
