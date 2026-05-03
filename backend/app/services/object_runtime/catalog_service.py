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

def _default_mention_token(record: ObjectInstanceRecord) -> str:
    if record.mention_tokens:
        return record.mention_tokens[0]
    return f"@object:{record.ref.object_id}"

def _score_mention_record(record: ObjectInstanceRecord, query: str) -> float:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return 0.1
    token = _default_mention_token(record).lower()
    title = record.title.lower()
    object_id = record.ref.object_id.lower()
    if token.startswith(f"@{normalized_query}") or token.startswith(normalized_query):
        return 1.0
    if title.startswith(normalized_query) or object_id.startswith(normalized_query):
        return 0.9
    haystack = " ".join(
        [
            title,
            object_id,
            record.ref.uri.lower(),
            record.mention_text.lower(),
            record.search_text.lower(),
        ]
    )
    return 0.6 if normalized_query in haystack else 0.0

def _to_mention_completion_item(
    record: ObjectInstanceRecord,
    *,
    query: str,
) -> ObjectMentionCompletionItem:
    token = _default_mention_token(record)
    return ObjectMentionCompletionItem(
        id=f"{record.ref.owner_pack}:{record.ref.object_kind}:{record.ref.object_id}",
        token=token,
        label=record.title,
        description=record.subtitle or record.summary_text or record.ref.uri,
        ref=record.ref,
        owner_pack=record.ref.owner_pack,
        object_kind=record.ref.object_kind,
        score=_score_mention_record(record, query),
        metadata={
            "labels": record.labels,
            "affordance_verbs": record.affordance_verbs,
            "stale": record.stale,
            "owner_surface_url": record.owner_surface_url,
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
    del include_examples

    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    entries = [
        _to_catalog_entry(entry)
        for entry in registry.list_entries(
            owner_pack=owner_pack,
            object_kind=object_kind,
            supports=supports,
        )
    ]

    return ObjectCatalogResponse(
        workspace_id=workspace_id,
        catalog_version=registry.get_catalog_version(),
        entries=entries,
    )


async def index_workspace_objects(
    request: ObjectInstanceIndexRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectInstanceIndexResponse:
    await _ensure_workspace_exists(workspace_id)
    catalog = _get_object_catalog_registry()
    for record in request.records:
        _validate_object_ref_identity(record.ref, workspace_id)
        if not catalog.get_entry(record.ref.owner_pack, record.ref.object_kind):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "object_kind_not_declared",
                    "message": "Indexed object kind must be declared in the object catalog.",
                    "details": {
                        "owner_pack": record.ref.owner_pack,
                        "object_kind": record.ref.object_kind,
                    },
                },
            )

    indexed_count = _get_object_instance_registry_store().upsert_many(
        workspace_id,
        request.records,
    )
    return ObjectInstanceIndexResponse(
        workspace_id=workspace_id,
        indexed_count=indexed_count,
    )


async def sync_workspace_object_index(
    request: ObjectInstanceSyncRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectInstanceSyncResponse:
    await _ensure_workspace_exists(workspace_id)
    return await get_object_index_sync_service().sync_workspace(
        workspace_id,
        request,
    )


async def get_workspace_object_index_sync_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> Dict[str, Any]:
    await _ensure_workspace_exists(workspace_id)
    return get_object_index_sync_status().snapshot(workspace_id=workspace_id)


async def index_workspace_object_relations(
    request: ObjectRelationIndexRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectRelationIndexResponse:
    await _ensure_workspace_exists(workspace_id)
    for relation in request.relations:
        _validate_object_ref_identity(relation.source_ref, workspace_id)
        _validate_object_ref_identity(relation.target_ref, workspace_id)

    indexed_count = _get_object_relation_registry_store().upsert_many(
        workspace_id,
        request.relations,
    )
    return ObjectRelationIndexResponse(
        workspace_id=workspace_id,
        indexed_count=indexed_count,
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
    await _ensure_workspace_exists(workspace_id)
    records = _get_object_relation_registry_store().search(
        workspace_id=workspace_id,
        object_uri=object_uri,
        source_uri=source_uri,
        target_uri=target_uri,
        relation_kind=relation_kind,
        meeting_id=meeting_id,
        limit=limit,
    )
    return ObjectRelationSearchResponse(
        workspace_id=workspace_id,
        results=records,
    )


async def search_workspace_objects(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    query: str = Query("", description="Search text or mention fragment"),
    owner_pack: str | None = Query(None, description="Filter by owner pack"),
    object_kind: str | None = Query(None, description="Filter by object kind"),
    limit: int = Query(20, ge=1, le=100, description="Maximum result count"),
) -> ObjectSearchResponse:
    await _ensure_workspace_exists(workspace_id)
    results = _get_object_instance_registry_store().search(
        workspace_id=workspace_id,
        query=query,
        owner_pack=owner_pack,
        object_kind=object_kind,
        limit=limit,
    )
    return ObjectSearchResponse(
        workspace_id=workspace_id,
        query=query,
        results=results,
    )


async def read_workspace_object(
    request: ObjectReadRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectReadResponse:
    await _ensure_workspace_exists(workspace_id)
    ref = _coerce_read_object_ref(request.object_ref, workspace_id)
    registry = _get_object_catalog_registry()
    _validate_catalog_object_ref(
        registry=registry,
        workspace_id=workspace_id,
        ref=ref,
        error_code="object_kind_not_declared",
    )
    record = _get_object_instance_registry_store().get_by_uri(
        workspace_id=workspace_id,
        uri=ref.uri,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "object_not_indexed",
                "message": "ObjectRef was valid but no concrete workspace object instance is indexed.",
                "details": {
                    "uri": ref.uri,
                    "workspace_id": workspace_id,
                },
            },
        )
    return ObjectReadResponse(workspace_id=workspace_id, object=record)


async def complete_workspace_objects(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    query: str = Query("", description="Mention query without the leading @"),
    owner_pack: str | None = Query(None, description="Filter by owner pack"),
    object_kind: str | None = Query(None, description="Filter by object kind"),
    limit: int = Query(20, ge=1, le=50, description="Maximum result count"),
) -> ObjectMentionCompletionResponse:
    await _ensure_workspace_exists(workspace_id)
    records = _get_object_instance_registry_store().search(
        workspace_id=workspace_id,
        query=query,
        owner_pack=owner_pack,
        object_kind=object_kind,
        limit=limit,
    )
    results = sorted(
        (_to_mention_completion_item(record, query=query) for record in records),
        key=lambda item: item.score,
        reverse=True,
    )
    return ObjectMentionCompletionResponse(
        workspace_id=workspace_id,
        query=query,
        results=results,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
