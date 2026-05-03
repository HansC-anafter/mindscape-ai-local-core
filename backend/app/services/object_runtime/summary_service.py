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

def _build_object_summary(
    *,
    entry: ObjectCatalogEntry,
    ref: ObjectRef,
    request: SelectionResolveRequest,
) -> ObjectSummary:
    subtitle_parts: List[str] = []
    if request.element and request.element.label:
        subtitle_parts.append(request.element.label)
    if request.surface.surface_id:
        subtitle_parts.append(request.surface.surface_id)

    summary_parts: List[str] = []
    if request.element and request.element.label:
        summary_parts.append(f"Selection label: {request.element.label}.")
    if request.surface.route:
        summary_parts.append(f"Owner surface: {request.surface.route}.")

    labels = sorted({"selection", ref.owner_pack, ref.object_kind})

    return ObjectSummary(
        ref=ref,
        title=f"{entry.display_name} {ref.object_id}",
        subtitle=" / ".join(subtitle_parts) or None,
        summary_text=" ".join(summary_parts) or None,
        status="ready",
        labels=labels,
        owner_surface_url=request.surface.route,
    )

def _build_catalog_summary(
    *,
    entry: ObjectCatalogEntry,
    ref: ObjectRef,
) -> ObjectSummary:
    return ObjectSummary(
        ref=ref,
        title=f"{entry.display_name} {ref.object_id}",
        summary_text=f"Addressable object from {ref.owner_pack}.{ref.object_kind}.",
        status="ready",
        labels=sorted({"meeting", ref.owner_pack, ref.object_kind}),
    )

def _first_text(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(payload.get(key))
        if value:
            return value
    return ""

def _coerce_summary_from_backend_payload(
    *,
    payload: Dict[str, Any],
    ref: ObjectRef,
    fallback_summary: ObjectSummary,
) -> ObjectSummary:
    title = _first_text(payload, "title", "display_label", "label")
    if not title:
        title = fallback_summary.title

    subtitle = _first_text(payload, "subtitle")
    if not subtitle:
        subtitle_parts: List[str] = []
        source_handle = _text(payload.get("source_handle"))
        source_shortcode = _text(payload.get("source_shortcode"))
        if source_handle:
            subtitle_parts.append(source_handle)
        if source_shortcode:
            subtitle_parts.append(f"#{source_shortcode}")
        if not subtitle_parts:
            for key in ("project_id", "run_id", "session_id", "scene_id", "artifact_id"):
                value = _text(payload.get(key))
                if value:
                    subtitle_parts.append(value)
                if len(subtitle_parts) >= 3:
                    break
        subtitle = " / ".join(subtitle_parts) or fallback_summary.subtitle or ""

    summary_text = _first_text(
        payload,
        "summary_text",
        "scene_summary",
        "summary",
        "review_summary",
        "post_caption",
    )
    if not summary_text:
        summary_text = fallback_summary.summary_text or ""

    status = _first_text(
        payload,
        "status",
        "analysis_status",
        "editorial_status",
        "approval_state",
    ) or (fallback_summary.status or "")

    labels = sorted(
        {
            *list(fallback_summary.labels or []),
            *_string_list(payload.get("labels"), limit=8),
            *_string_list(payload.get("tags"), limit=8),
            *_string_list(payload.get("auto_tags"), limit=8),
        }
    )
    thumbnail_ref = _first_text(payload, "thumbnail_ref", "thumbnail_url", "image_url")
    owner_surface_url = _first_text(payload, "owner_surface_url") or (
        fallback_summary.owner_surface_url or ""
    )
    updated_at = _first_text(payload, "updated_at")

    return ObjectSummary(
        ref=ref,
        title=title,
        subtitle=subtitle or None,
        summary_text=summary_text or None,
        status=status or None,
        labels=labels,
        thumbnail_ref=thumbnail_ref or None,
        owner_surface_url=owner_surface_url or None,
        updated_at=updated_at or None,
    )

def _select_summary_backend(entry_payload: Dict[str, Any]) -> str | None:
    resolver_backends = dict(entry_payload.get("resolver_backends") or {})
    backend = _text(resolver_backends.get("summary_backend"))
    return backend or None

async def _resolve_runtime_summary(
    *,
    entry_payload: Dict[str, Any],
    workspace_id: str,
    ref: ObjectRef,
    fallback_summary: ObjectSummary,
) -> ObjectSummary:
    backend = _select_summary_backend(entry_payload)
    if not backend:
        return fallback_summary

    try:
        payload = await _invoke_backend_callable(
            backend,
            workspace_id=workspace_id,
            object_id=ref.object_id,
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception(
            "Failed to resolve object summary via %s for %s: %s",
            backend,
            ref.uri,
            exc,
        )
        return fallback_summary

    if not isinstance(payload, dict):
        return fallback_summary

    return _coerce_summary_from_backend_payload(
        payload=payload,
        ref=ref,
        fallback_summary=fallback_summary,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
