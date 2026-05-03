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

def _relation_record_to_graph_relation(
    record: ObjectRelationRecord,
    *,
    origin_uri: str,
) -> ObjectGraphRelation:
    if record.source_ref.uri == origin_uri:
        direction = "outbound"
        target_ref = record.target_ref
    else:
        direction = "inbound"
        target_ref = record.source_ref
    return ObjectGraphRelation(
        relation_kind=record.relation_kind,
        direction=direction,
        target_ref=target_ref,
        metadata={
            **dict(record.metadata or {}),
            "relation_id": record.relation_id,
            "source_role": record.source_role,
            "target_role": record.target_role,
            "provenance_type": record.provenance_type,
            "provenance_id": record.provenance_id,
            "meeting_id": record.meeting_id,
            "projection_source": "object_relation_registry",
        },
    )

def _select_graph_projection_backend(entry_payload: Dict[str, Any]) -> str | None:
    for projection in list(entry_payload.get("graph_projection_backends") or []):
        backend = _text(projection.get("backend"))
        if backend:
            return backend
    return None

def _coerce_relation_target_ref(
    raw_relation: Dict[str, Any],
    *,
    workspace_id: str,
) -> ObjectRef | None:
    nested_target = raw_relation.get("target_ref")
    if not isinstance(nested_target, dict):
        nested_target = raw_relation.get("to_ref")
    nested_target = dict(nested_target) if isinstance(nested_target, dict) else {}

    owner_pack = _text(
        nested_target.get("owner_pack")
        or nested_target.get("target_owner_pack")
        or nested_target.get("target_pack")
        or raw_relation.get("target_owner_pack")
        or raw_relation.get("target_pack")
    )
    object_kind = _text(
        nested_target.get("object_kind")
        or nested_target.get("target_object_kind")
        or nested_target.get("target_kind")
        or raw_relation.get("target_object_kind")
        or raw_relation.get("target_kind")
    )
    object_id = _text(
        nested_target.get("object_id")
        or nested_target.get("target_object_id")
        or raw_relation.get("target_object_id")
    )
    uri = _text(nested_target.get("uri") or raw_relation.get("target_uri"))
    parsed_owner_pack, parsed_object_kind, parsed_object_id = _parse_mindscape_uri(uri)
    owner_pack = owner_pack or (parsed_owner_pack or "")
    object_kind = object_kind or (parsed_object_kind or "")
    object_id = object_id or (parsed_object_id or "")
    if not owner_pack or not object_kind or not object_id:
        return None
    return ObjectRef(
        uri=uri or f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id=workspace_id,
        version=_text(nested_target.get("version")) or None,
        selector=nested_target.get("selector"),
        source_surface=_text(nested_target.get("source_surface")) or None,
    )

def _normalize_graph_relations(
    raw_relations: Any,
    *,
    workspace_id: str,
) -> List[ObjectGraphRelation]:
    normalized_relations: List[ObjectGraphRelation] = []
    relation_items = list(raw_relations or []) if isinstance(raw_relations, list) else []
    known_keys = {
        "relation_kind",
        "kind",
        "direction",
        "target_ref",
        "to_ref",
        "target_uri",
        "target_owner_pack",
        "target_pack",
        "target_object_kind",
        "target_kind",
        "target_object_id",
    }
    for raw_relation in relation_items:
        if not isinstance(raw_relation, dict):
            continue
        relation_kind = _text(raw_relation.get("relation_kind") or raw_relation.get("kind"))
        target_ref = _coerce_relation_target_ref(raw_relation, workspace_id=workspace_id)
        if not relation_kind or target_ref is None:
            continue
        direction = _text(raw_relation.get("direction")) or "outbound"
        if direction not in {"outbound", "inbound", "bidirectional"}:
            direction = "outbound"
        metadata = {
            key: value
            for key, value in raw_relation.items()
            if key not in known_keys and value is not None
        }
        normalized_relations.append(
            ObjectGraphRelation(
                relation_kind=relation_kind,
                direction=direction,
                target_ref=target_ref,
                metadata=metadata,
            )
        )
    return normalized_relations

def _coerce_guidance_ref(raw_ref: Any, *, workspace_id: str) -> ObjectRef | None:
    if not isinstance(raw_ref, dict):
        return None
    payload = dict(raw_ref)
    uri = _text(payload.get("uri"))
    parsed_owner_pack, parsed_object_kind, parsed_object_id = _parse_mindscape_uri(uri)
    if parsed_owner_pack and parsed_object_kind and parsed_object_id:
        payload.setdefault("owner_pack", parsed_owner_pack)
        payload.setdefault("object_kind", parsed_object_kind)
        payload.setdefault("object_id", parsed_object_id)
    try:
        return _coerce_materialized_ref_payload(payload, workspace_id=workspace_id)
    except Exception:
        return None

def _normalize_guidance_cards(raw_guidance: Any, *, workspace_id: str) -> List[ObjectGuidanceCard]:
    normalized_cards: List[ObjectGuidanceCard] = []
    guidance_items = list(raw_guidance or []) if isinstance(raw_guidance, list) else []
    known_keys = {
        "id",
        "title",
        "label",
        "description",
        "summary",
        "intent",
        "command_template",
        "command",
        "review_label",
        "review_route",
        "review_routes",
        "proposal_ref",
        "proposal",
        "target_ref",
        "target",
        "required_roles",
        "priority",
    }
    for index, raw_card in enumerate(guidance_items):
        if not isinstance(raw_card, dict):
            continue
        title = _text(raw_card.get("title") or raw_card.get("label"))
        if not title:
            continue
        priority = raw_card.get("priority")
        if not isinstance(priority, int):
            priority = 100 + index
        metadata = {
            key: value
            for key, value in raw_card.items()
            if key not in known_keys and value is not None
        }
        normalized_cards.append(
            ObjectGuidanceCard(
                id=_text(raw_card.get("id")) or f"guidance_{index + 1}",
                title=title,
                description=_text(raw_card.get("description") or raw_card.get("summary"))
                or None,
                intent=_text(raw_card.get("intent")) or None,
                command_template=_text(
                    raw_card.get("command_template") or raw_card.get("command")
                )
                or None,
                review_label=_text(raw_card.get("review_label")) or None,
                review_routes=_coerce_route_list(
                    raw_card,
                    single_key="review_route",
                    plural_key="review_routes",
                ),
                proposal_ref=_coerce_guidance_ref(
                    raw_card.get("proposal_ref") or raw_card.get("proposal"),
                    workspace_id=workspace_id,
                ),
                target_ref=_coerce_guidance_ref(
                    raw_card.get("target_ref") or raw_card.get("target"),
                    workspace_id=workspace_id,
                ),
                required_roles=_string_list(raw_card.get("required_roles"), limit=8),
                priority=priority,
                metadata=metadata,
            )
        )
    return sorted(normalized_cards, key=lambda card: (card.priority, card.id))

async def _resolve_graph_projection(
    *,
    entry_payload: Dict[str, Any],
    workspace_id: str,
    ref: ObjectRef,
    allow_registry_fallback: bool = False,
) -> Dict[str, Any]:
    backend_path = _select_graph_projection_backend(entry_payload)
    if not backend_path:
        if allow_registry_fallback:
            return {}
        raise HTTPException(
            status_code=422,
            detail={
                "code": "projection_unavailable",
                "message": "Graph projection is unavailable for this object kind.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                },
            },
        )

    try:
        result = await _invoke_backend_callable(
            backend_path,
            workspace_id=workspace_id,
            object_id=ref.object_id,
        )
    except Exception as exc:
        logger.exception(
            "Addressable Object Layer graph projection failed for %s.%s",
            ref.owner_pack,
            ref.object_kind,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "graph_projection_failed",
                "message": (
                    "Owner-pack graph projection failed while building the runtime graph."
                ),
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                    "error": str(exc),
                },
            },
        ) from exc

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_graph_projection",
                "message": "Owner-pack graph projection returned a non-object payload.",
                "details": {
                    "owner_pack": ref.owner_pack,
                    "object_kind": ref.object_kind,
                },
            },
        )
    return result


async def project_object_graph(
    request: ObjectGraphProjectRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
) -> ObjectGraphProjectResponse:
    await _ensure_workspace_exists(workspace_id)
    registry = _get_object_catalog_registry()
    projections: List[ObjectGraphProjection] = []

    for ref in request.objects:
        entry, fallback_summary = await _resolve_attach_ref(
            registry=registry,
            workspace_id=workspace_id,
            ref=ref,
            require_meeting_projection=False,
            error_code="object_not_found",
        )
        entry_payload = registry.get_entry(ref.owner_pack, ref.object_kind) or {}
        raw_projection = await _resolve_graph_projection(
            entry_payload=entry_payload,
            workspace_id=workspace_id,
            ref=ref,
            allow_registry_fallback=True,
        )
        metadata = {
            "projection_source": (
                "owner_pack_graph_projection"
                if raw_projection
                else "object_relation_registry"
            ),
            **{
                key: value
                for key, value in raw_projection.items()
                if (
                    key
                    not in {
                        "node_kind",
                        "relations",
                        "guidance",
                        "display_label",
                        "summary_text",
                    }
                    and value is not None
                )
            },
        }
        graph_relations: List[ObjectGraphRelation] = []
        if request.include_relations:
            graph_relations.extend(
                _normalize_graph_relations(
                    raw_projection.get("relations"),
                    workspace_id=workspace_id,
                )
            )
            try:
                graph_relations.extend(
                    _relation_record_to_graph_relation(record, origin_uri=ref.uri)
                    for record in _get_object_relation_registry_store().search(
                        workspace_id=workspace_id,
                        object_uri=ref.uri,
                        limit=100,
                    )
                )
            except Exception:
                logger.exception(
                    "Addressable Object Layer persisted relation projection failed for %s",
                    ref.uri,
                )
        projection_summary = fallback_summary if request.include_summaries else None
        projections.append(
            ObjectGraphProjection(
                ref=ref,
                summary=projection_summary,
                node_kind=_text(raw_projection.get("node_kind")) or entry.object_kind,
                relations=graph_relations,
                guidance=_normalize_guidance_cards(
                    raw_projection.get("guidance"),
                    workspace_id=workspace_id,
                ),
                metadata=metadata,
            )
        )

    return ObjectGraphProjectResponse(
        workspace_id=workspace_id,
        projections=projections,
    )


__all__ = [name for name in globals() if name.startswith("_") and not name.startswith("__")]
__all__.extend([name for name in globals() if not name.startswith("_") and callable(globals()[name])])
