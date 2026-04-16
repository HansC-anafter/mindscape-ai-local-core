from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.task_ir import ArtifactReference
from backend.shared.schemas.spatial_scheduling import (
    SpatialAnchor,
    SpatialEntityRef,
    SpatialScheduleSegment,
    SpatialSchedulingIR,
)


SPATIAL_SCHEDULE_ARTIFACT_MIME = "application/vnd.mindscape.spatial-scheduling+json"
SPATIAL_SCHEDULE_SESSION_KEY = "spatial_schedule_context"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return dict(value) if isinstance(value, dict) else {}


def _normalize_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in value:
        item_dict = _normalize_dict(item)
        if item_dict:
            normalized.append(item_dict)
    return normalized


def _normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if value in (None, ""):
        return []
    text = str(value).strip()
    return [text] if text else []


def _governance_dict(governance: Any) -> Dict[str, Any]:
    if governance is None:
        return {}
    if hasattr(governance, "model_dump"):
        governance = governance.model_dump(mode="json")
    return dict(governance) if isinstance(governance, dict) else {}


def _deliverables_include_spatial_schedule(governance: Dict[str, Any]) -> bool:
    for deliverable in _normalize_dict_list(governance.get("deliverables")):
        mime_type = str(deliverable.get("mime_type") or "").strip().lower()
        if mime_type == SPATIAL_SCHEDULE_ARTIFACT_MIME:
            return True
    return False


def _spatial_schedule_request(governance: Dict[str, Any]) -> Dict[str, Any]:
    constraints = _normalize_dict(governance.get("governance_constraints"))
    request = _normalize_dict(constraints.get("spatial_schedule"))
    return request


def should_emit_spatial_schedule(governance: Any) -> bool:
    governance_dict = _governance_dict(governance)
    request = _spatial_schedule_request(governance_dict)
    if request.get("requested") is True:
        return True
    if _deliverables_include_spatial_schedule(governance_dict):
        return True
    requested_output_type = (
        str(governance_dict.get("requested_output_type") or "").strip().lower()
    )
    return requested_output_type == SPATIAL_SCHEDULE_ARTIFACT_MIME


def _extract_entity_ref(raw: Dict[str, Any], default_id: str, default_name: str) -> SpatialEntityRef:
    actor_id = str(raw.get("actor_id") or "").strip()
    object_id = str(raw.get("object_id") or "").strip()
    entity_id = (
        str(raw.get("entity_id") or "").strip()
        or actor_id
        or object_id
        or default_id
    )
    entity_kind = (
        str(raw.get("entity_kind") or raw.get("subject_kind") or "").strip()
        or ("actor" if actor_id else "object" if object_id else "task_phase")
    )
    display_name = str(raw.get("display_name") or raw.get("title") or default_name).strip()
    return SpatialEntityRef(
        entity_id=entity_id,
        entity_kind=entity_kind,
        display_name=display_name or None,
        role=str(raw.get("role") or "").strip() or None,
        tags=_normalize_string_list(raw.get("tags") or raw.get("intent_tags")),
        metadata={
            key: value
            for key, value in raw.items()
            if key
            not in {
                "entity_id",
                "entity_kind",
                "subject_kind",
                "actor_id",
                "object_id",
                "display_name",
                "title",
                "role",
                "tags",
                "intent_tags",
            }
        },
    )


def _extract_anchor_ids(raw: Dict[str, Any]) -> List[str]:
    anchors: List[str] = []
    for anchor in _normalize_dict_list(raw.get("anchors")):
        anchor_id = str(anchor.get("anchor_id") or anchor.get("id") or "").strip()
        if anchor_id:
            anchors.append(anchor_id)
    return anchors


def _extract_motion_constraint_objects(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    objects = raw.get("motion_constraint_objects")
    if not isinstance(objects, list):
        return []
    return [item for item in (_normalize_dict(obj) for obj in objects) if item]


def _extract_consumer_hints(governance: Dict[str, Any]) -> List[str]:
    request = _spatial_schedule_request(governance)
    hints = _normalize_string_list(request.get("consumer_hints"))
    if hints:
        return hints
    return _normalize_string_list(request.get("targets"))


def _extract_anchors(raw_items: Iterable[Dict[str, Any]]) -> List[SpatialAnchor]:
    anchors_by_id: Dict[str, SpatialAnchor] = {}
    for raw in raw_items:
        for anchor in _normalize_dict_list(raw.get("anchors")):
            anchor_id = str(anchor.get("anchor_id") or anchor.get("id") or "").strip()
            if not anchor_id or anchor_id in anchors_by_id:
                continue
            anchors_by_id[anchor_id] = SpatialAnchor(
                anchor_id=anchor_id,
                anchor_kind=str(anchor.get("anchor_kind") or anchor.get("kind") or "logical").strip(),
                label=str(anchor.get("label") or "").strip() or None,
                metadata={
                    key: value
                    for key, value in anchor.items()
                    if key not in {"anchor_id", "id", "anchor_kind", "kind", "label"}
                },
            )
    return list(anchors_by_id.values())


def build_spatial_scheduling_ir(
    *,
    workspace_id: str,
    decision: str,
    action_items: List[Dict[str, Any]],
    action_intents: Optional[List[Any]] = None,
    governance: Any = None,
    task_id: str,
    session_id: Optional[str] = None,
) -> SpatialSchedulingIR:
    governance_dict = _governance_dict(governance)
    request = _spatial_schedule_request(governance_dict)
    source_items: List[Dict[str, Any]] = []

    if action_intents:
        for intent in action_intents:
            source_items.append(
                {
                    "intent_id": getattr(intent, "intent_id", None),
                    "title": getattr(intent, "title", None),
                    "description": getattr(intent, "description", None),
                    "entity_id": getattr(intent, "entity_id", None),
                    "entity_kind": getattr(intent, "entity_kind", None),
                    "tags": getattr(intent, "intent_tags", None),
                    "anchors": getattr(intent, "anchors", None),
                    "motion_constraint_objects": getattr(
                        intent, "motion_constraint_objects", None
                    ),
                }
            )
    else:
        source_items.extend(_normalize_dict_list(action_items))

    entities_by_id: Dict[str, SpatialEntityRef] = {}
    segments: List[SpatialScheduleSegment] = []

    for index, raw in enumerate(source_items, start=1):
        title = str(raw.get("title") or raw.get("action") or f"Segment {index}").strip()
        description = str(
            raw.get("description") or raw.get("detail") or raw.get("summary") or ""
        ).strip()
        intent_id = str(raw.get("intent_id") or "").strip() or None
        entity_ref = _extract_entity_ref(
            raw,
            default_id=intent_id or f"segment_entity_{index}",
            default_name=title,
        )
        entities_by_id.setdefault(entity_ref.entity_id, entity_ref)
        motion_constraint_objects = _extract_motion_constraint_objects(raw)
        segments.append(
            SpatialScheduleSegment(
                segment_id=f"segment_{index}",
                order=index - 1,
                title=title,
                description=description or None,
                intent_id=intent_id,
                entity_refs=[entity_ref.entity_id],
                intent_tags=_normalize_string_list(raw.get("intent_tags") or raw.get("tags")),
                anchors=_extract_anchor_ids(raw),
                motion_constraint_objects=motion_constraint_objects,
                metadata={
                    key: value
                    for key, value in raw.items()
                    if key
                    not in {
                        "title",
                        "action",
                        "description",
                        "detail",
                        "summary",
                        "intent_id",
                        "intent_tags",
                        "tags",
                        "anchors",
                        "motion_constraint_objects",
                    }
                },
            )
        )

    motion_constraint_count = sum(
        len(segment.motion_constraint_objects) for segment in segments
    )
    constraint_summary = {
        "motion_constraint_count": motion_constraint_count,
        "segment_count": len(segments),
    }
    for key, value in _normalize_dict(request.get("constraint_summary")).items():
        constraint_summary[key] = value

    return SpatialSchedulingIR(
        workspace_id=workspace_id,
        title=str(request.get("title") or decision or "Spatial schedule").strip() or None,
        decision=decision or None,
        entities=list(entities_by_id.values()),
        anchors=_extract_anchors(source_items),
        segments=segments,
        consumer_hints=_extract_consumer_hints(governance_dict),
        constraint_summary=constraint_summary,
        metadata={
            "source_task_id": task_id,
            "source_session_id": session_id,
            "emission_trigger": (
                "governance_constraints"
                if request.get("requested") is True
                else "deliverable"
                if _deliverables_include_spatial_schedule(governance_dict)
                else "requested_output_type"
            ),
        },
    )


def create_spatial_schedule_artifact(
    *,
    schedule: SpatialSchedulingIR,
    task_id: str,
) -> ArtifactReference:
    artifact_id = f"{task_id}/artifacts/spatial_schedule"
    return ArtifactReference(
        id=artifact_id,
        type=SPATIAL_SCHEDULE_ARTIFACT_MIME,
        source="meeting:spatial_scheduling",
        uri=f"task-ir://{task_id}/artifacts/spatial_schedule",
        metadata={
            "schedule_id": schedule.schedule_id,
            "schema_version": schedule.schema_version,
            "segment_count": len(schedule.segments),
            "consumer_hints": list(schedule.consumer_hints),
            "content_json": schedule.model_dump(mode="json"),
        },
    )


def build_spatial_schedule_context(
    schedule: SpatialSchedulingIR,
    artifact: ArtifactReference,
) -> Dict[str, Any]:
    entity_kinds = sorted(
        {
            str(entity.entity_kind).strip()
            for entity in schedule.entities
            if str(entity.entity_kind).strip()
        }
    )
    return {
        "schedule_id": schedule.schedule_id,
        "status": schedule.status,
        "title": schedule.title,
        "source_task_id": schedule.metadata.get("source_task_id"),
        "source_session_id": schedule.metadata.get("source_session_id"),
        "source_artifact_id": artifact.id,
        "entity_kinds": entity_kinds,
        "active_segment_ids": [segment.segment_id for segment in schedule.segments[:5]],
        "segment_count": len(schedule.segments),
        "time_window": (
            {
                "start_index": 0,
                "end_index": len(schedule.segments) - 1,
            }
            if schedule.segments
            else {}
        ),
        "consumer_refs": [],
        "constraint_summary": dict(schedule.constraint_summary),
        "artifact_refs": [
            {
                "artifact_id": artifact.id,
                "artifact_type": artifact.type,
                "uri": artifact.uri,
            }
        ],
        "updated_at": _utc_now_iso(),
    }


def persist_spatial_schedule_context_to_session(
    *,
    session: Any,
    workspace_id: str,
    spatial_schedule_context: Dict[str, Any],
) -> None:
    metadata = dict(getattr(session, "metadata", {}) or {})
    metadata[SPATIAL_SCHEDULE_SESSION_KEY] = dict(spatial_schedule_context)
    setattr(session, "metadata", metadata)
    _refresh_world_sidecars(session=session, workspace_id=workspace_id)


def _refresh_world_sidecars(*, session: Any, workspace_id: str) -> None:
    metadata = dict(getattr(session, "metadata", {}) or {})
    governance_context = _normalize_dict(metadata.get("governance_context"))
    memory_packet = _normalize_dict(metadata.get("memory_packet"))
    if not governance_context or not memory_packet:
        return

    try:
        from backend.app.system_capabilities.world_memory_core.services.context_export_facade import (
            ContextExportFacade,
        )

        rebuilt = ContextExportFacade().export_context(
            workspace_id=workspace_id,
            profile_id=str(metadata.get("profile_id") or "").strip() or None,
            project_id=getattr(session, "project_id", None),
            session_id=getattr(session, "id", None),
            governance_context=governance_context,
            memory_packet=memory_packet,
            receipt=_normalize_dict(metadata.get("world_memory_packet")),
            geo_context=_normalize_dict(metadata.get("geo_context")),
            motion_context=_normalize_dict(metadata.get("motion_context")),
            spatial_schedule_context=_normalize_dict(
                metadata.get(SPATIAL_SCHEDULE_SESSION_KEY)
            ),
        )
    except Exception:
        return

    if not isinstance(rebuilt, dict):
        return

    for key in (
        "world_memory_packet",
        "world_card_projection",
        "world_card_text",
        "geo_context",
        "motion_context",
        SPATIAL_SCHEDULE_SESSION_KEY,
    ):
        if key in rebuilt and rebuilt.get(key):
            metadata[key] = rebuilt.get(key)

    setattr(session, "metadata", metadata)
