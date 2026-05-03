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
from backend.app.services.object_runtime.summary_service import *

def _default_meeting_projection_payload(
    *,
    ref: ObjectRef,
    summary: ObjectSummary,
    verb: str,
) -> Dict[str, Any]:
    return {
        "verb": _text(verb) or "attach",
        "uri": ref.uri,
        "owner_pack": ref.owner_pack,
        "object_kind": ref.object_kind,
        "object_id": ref.object_id,
        "title": summary.title,
        "summary_text": summary.summary_text,
        "labels": list(summary.labels or []),
    }

def _select_meeting_projection_backend(
    entry_payload: Dict[str, Any],
    *,
    verb: str,
) -> str | None:
    for projection in list(entry_payload.get("meeting_projection_backends") or []):
        verbs = list(projection.get("verbs") or [])
        backend = _text(projection.get("projection_backend"))
        if backend and verb in verbs:
            return backend

    for projection in list(entry_payload.get("meeting_projection_backends") or []):
        backend = _text(projection.get("projection_backend"))
        if backend:
            return backend

    return None

def _build_materializer_context_objects(
    context_records: List[ObjectMeetingContextRecord],
    *,
    roles: set[str] | None = None,
) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for record in context_records:
        if roles is not None and record.role not in roles:
            continue
        payload = {
            "role": record.role,
            "owner_pack": record.ref.owner_pack,
            "object_kind": record.ref.object_kind,
            "object_id": record.ref.object_id,
            "object_ref": record.ref.model_dump(exclude_none=True),
            "object_summary": {
                "title": record.summary.title,
                "subtitle": record.summary.subtitle,
                "summary_text": record.summary.summary_text,
                "status": record.summary.status,
                "labels": list(record.summary.labels or []),
                "owner_surface_url": record.summary.owner_surface_url,
            },
        }
        if isinstance(record.meeting_projection, dict) and record.meeting_projection:
            payload["meeting_projection"] = dict(record.meeting_projection)

        payloads.append(
            {
                **payload,
            }
        )
    return payloads

async def _resolve_meeting_projection_payload(
    *,
    entry_payload: Dict[str, Any],
    workspace_id: str,
    ref: ObjectRef,
    summary: ObjectSummary,
    verb: str,
) -> Dict[str, Any]:
    backend_path = _select_meeting_projection_backend(entry_payload, verb=verb)
    if not backend_path:
        return _default_meeting_projection_payload(ref=ref, summary=summary, verb=verb)

    try:
        result = await _invoke_backend_callable(
            backend_path,
            workspace_id=workspace_id,
            object_id=ref.object_id,
            verb=verb,
        )
    except Exception:
        logger.exception(
            "Addressable Object Layer meeting projection failed for %s.%s",
            ref.owner_pack,
            ref.object_kind,
        )
        return _default_meeting_projection_payload(ref=ref, summary=summary, verb=verb)

    if isinstance(result, dict) and result:
        return result

    return _default_meeting_projection_payload(ref=ref, summary=summary, verb=verb)

async def _resolve_attach_ref(
    *,
    registry: ObjectCatalogRegistry,
    workspace_id: str,
    ref: ObjectRef,
    require_meeting_projection: bool,
    error_code: str,
) -> Tuple[ObjectCatalogEntry, ObjectSummary]:
    _validate_object_ref_identity(ref, workspace_id)

    entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind)
    if not entry_payload:
        raise HTTPException(
            status_code=404,
            detail={
                "code": error_code,
                "message": (
                    "ObjectRef does not map to an installed addressable object kind."
                ),
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                    "object_id": ref.object_id,
                },
            },
        )

    entry = _to_catalog_entry(entry_payload)
    if require_meeting_projection and not entry.meeting_projection_capabilities.available:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "projection_unavailable",
                "message": "Meeting attachment is unavailable for this object kind.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                },
            },
        )

    fallback_summary = _build_catalog_summary(entry=entry, ref=ref)
    summary = await _resolve_runtime_summary(
        entry_payload=entry_payload,
        workspace_id=workspace_id,
        ref=ref,
        fallback_summary=fallback_summary,
    )

    return entry, summary


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
