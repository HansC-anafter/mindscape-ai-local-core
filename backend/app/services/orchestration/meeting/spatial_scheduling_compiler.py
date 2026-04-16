"""Spatial scheduling compiler for meeting-produced TaskIR artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from backend.app.models.task_ir import ArtifactReference
from backend.shared.schemas.spatial_scheduling import (
    SPATIAL_SCHEDULING_SCHEMA_VERSION,
    SpatialAnchor,
    SpatialEntityRef,
    SpatialScheduleSegment,
    SpatialSchedulingIR,
)


SPATIAL_SCHEDULE_ARTIFACT_MIME = "application/vnd.mindscape.spatial-scheduling+json"
SPATIAL_SCHEDULE_COMPILER_VERSION = "2026-04-16.local-core.p0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def should_emit_spatial_schedule(governance: Optional[Dict[str, Any]]) -> bool:
    """Return True when governance explicitly requests a spatial schedule."""
    if not isinstance(governance, dict):
        return False

    constraints = governance.get("governance_constraints")
    if isinstance(constraints, dict):
        spatial_schedule = constraints.get("spatial_schedule")
        if isinstance(spatial_schedule, dict) and spatial_schedule.get("requested") is True:
            return True

    deliverables = governance.get("deliverables") or []
    for deliverable in deliverables:
        if not isinstance(deliverable, dict):
            continue
        mime_type = deliverable.get("mime_type") or deliverable.get("type")
        if mime_type == SPATIAL_SCHEDULE_ARTIFACT_MIME:
            return True

    return governance.get("requested_output_type") == SPATIAL_SCHEDULE_ARTIFACT_MIME


def build_spatial_scheduling_ir(
    *,
    task_id: str,
    workspace_id: str,
    session_id: str,
    decision: str,
    action_items: list[dict[str, Any]],
    action_intents: Optional[list[Any]] = None,
    governance: Optional[Dict[str, Any]] = None,
    world_context: Optional[Dict[str, Any]] = None,
) -> SpatialSchedulingIR:
    """Compile a provider-neutral spatial schedule from meeting outputs."""
    items = _normalize_source_items(action_items, action_intents)
    consumer_hints = _extract_consumer_hints(governance)
    entities = _collect_entities(items)
    anchors = _collect_anchors(items, world_context)
    segments = _build_segments(items, anchors)
    constraint_summary = _build_constraint_summary(
        items=items,
        governance=governance,
        consumer_hints=consumer_hints,
    )

    schedule = SpatialSchedulingIR(
        workspace_id=workspace_id,
        title=_derive_schedule_title(decision=decision, governance=governance),
        decision=decision,
        entities=entities,
        anchors=anchors,
        segments=segments,
        consumer_hints=consumer_hints,
        constraint_summary=constraint_summary,
        metadata={
            "source_task_id": task_id,
            "source_session_id": session_id,
            "timebase": _extract_timebase(world_context, items),
            "emission_reason": _derive_emission_reason(governance),
            "compiler_version": SPATIAL_SCHEDULE_COMPILER_VERSION,
            "operator_prompt_summary": _summarize_operator_prompt(governance),
            "world_context_refs": _extract_world_context_refs(world_context),
            "governance_snapshot": _build_governance_snapshot(governance),
            "source_conflicts": [],
        },
    )
    return schedule


def build_spatial_schedule_artifact(
    *,
    task_id: str,
    schedule: SpatialSchedulingIR,
) -> ArtifactReference:
    """Wrap a spatial schedule as a TaskIR artifact."""
    artifact_id = f"{task_id}/spatial_schedule"
    return ArtifactReference(
        id=artifact_id,
        type=SPATIAL_SCHEDULE_ARTIFACT_MIME,
        source="meeting:spatial_schedule",
        uri=f"task-ir://{task_id}/artifacts/spatial_schedule",
        metadata={
            "schedule_id": schedule.schedule_id,
            "schema_version": schedule.schema_version,
            "content_json": schedule.model_dump(mode="json"),
        },
    )


def build_spatial_schedule_context(
    *,
    schedule: SpatialSchedulingIR,
    artifact: ArtifactReference,
) -> Dict[str, Any]:
    """Build the canonical bounded schedule summary kept in session metadata."""
    entity_kinds = sorted(
        {
            entity.entity_kind
            for entity in schedule.entities
            if getattr(entity, "entity_kind", None)
        }
    )

    active_segments = []
    for segment in schedule.segments:
        active_segments.append(
            {
                "segment_id": segment.segment_id,
                "title": segment.title,
                "entity_refs": list(segment.entity_refs),
                "anchor_ids": list(segment.anchors),
            }
        )

    return {
        "schedule_id": schedule.schedule_id,
        "schema_version": schedule.schema_version,
        "status": schedule.status,
        "artifact_ref": {
            "artifact_id": artifact.id,
            "type": artifact.type,
        },
        "source_task_id": schedule.metadata.get("source_task_id"),
        "source_session_id": schedule.metadata.get("source_session_id"),
        "entity_kinds": entity_kinds,
        "active_segments": active_segments,
        "constraint_summary": dict(schedule.constraint_summary),
        "schedule_revision_refs": [],
        "consumer_receipts": {},
        "updated_at": _utc_now_iso(),
    }


def persist_spatial_schedule_context_to_session(
    session: Any,
    context: Dict[str, Any],
) -> None:
    """Persist the canonical schedule summary on the meeting session."""
    if getattr(session, "metadata", None) is None:
        session.metadata = {}
    session.metadata["spatial_schedule_context"] = context


def refresh_world_sidecars(session: Any, context: Dict[str, Any]) -> None:
    """Project the bounded schedule summary into lightweight world sidecars."""
    if getattr(session, "metadata", None) is None:
        session.metadata = {}
    metadata = session.metadata

    world_packet = dict(metadata.get("world_memory_packet") or {})
    world_packet["active_schedule"] = _build_active_schedule_projection(context)
    world_packet["schedule_artifact_refs"] = [dict(context.get("artifact_ref") or {})]
    world_packet["schedule_constraints"] = dict(context.get("constraint_summary") or {})
    metadata["world_memory_packet"] = world_packet

    projection = dict(metadata.get("world_card_projection") or {})
    summary_lines = list(projection.get("summary_lines") or [])
    schedule_line = _build_world_card_schedule_line(context)
    summary_lines = [line for line in summary_lines if not str(line).startswith("Active schedule:")]
    summary_lines.append(schedule_line)
    projection["summary_lines"] = summary_lines
    metadata["world_card_projection"] = projection

    world_card_lines = _split_world_card_lines(metadata.get("world_card_text"))
    world_card_lines = [line for line in world_card_lines if not line.startswith("Active schedule:")]
    world_card_lines.append(schedule_line)
    metadata["world_card_text"] = "\n".join(world_card_lines).strip()


def emit_spatial_schedule_for_task_ir(
    *,
    task_ir: Any,
    session: Optional[Any],
    decision: str,
    action_items: list[dict[str, Any]],
    action_intents: Optional[list[Any]],
) -> None:
    """Emit a spatial schedule artifact plus session sidecars for a compiled TaskIR."""
    governance = getattr(getattr(task_ir, "metadata", None), "governance", None)
    if not should_emit_spatial_schedule(governance):
        return

    session_id = getattr(session, "id", "") if session is not None else ""
    world_context = None
    if session is not None and isinstance(getattr(session, "metadata", None), dict):
        candidate_world_context = session.metadata.get("world_memory_packet")
        if isinstance(candidate_world_context, dict):
            world_context = candidate_world_context

    schedule = build_spatial_scheduling_ir(
        task_id=task_ir.task_id,
        workspace_id=task_ir.workspace_id,
        session_id=session_id,
        decision=decision,
        action_items=action_items,
        action_intents=action_intents,
        governance=governance,
        world_context=world_context,
    )
    artifact = build_spatial_schedule_artifact(task_id=task_ir.task_id, schedule=schedule)
    task_ir.artifacts.append(artifact)

    if session is None:
        return

    context = build_spatial_schedule_context(schedule=schedule, artifact=artifact)
    persist_spatial_schedule_context_to_session(session, context)
    refresh_world_sidecars(session, context)


def _normalize_source_items(
    action_items: list[dict[str, Any]],
    action_intents: Optional[list[Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if action_intents:
        for index, intent in enumerate(action_intents):
            items.append(
                {
                    "segment_id": getattr(intent, "intent_id", None) or f"seg_{index + 1:03d}",
                    "order": index,
                    "title": getattr(intent, "title", None) or f"Step {index + 1}",
                    "description": getattr(intent, "description", None),
                    "intent_id": getattr(intent, "intent_id", None),
                    "intent_tags": list(getattr(intent, "intent_tags", None) or []),
                    "motion_constraint_objects": list(
                        getattr(intent, "motion_constraint_objects", None) or []
                    ),
                    "entity_id": getattr(intent, "entity_id", None),
                    "entity_kind": getattr(intent, "entity_kind", None),
                    "entity_refs": list(getattr(intent, "entity_refs", None) or []),
                    "anchors": list(getattr(intent, "anchors", None) or []),
                    "metadata": dict(getattr(intent, "metadata", None) or {}),
                }
            )
    else:
        for index, item in enumerate(action_items):
            item = dict(item or {})
            items.append(
                {
                    "segment_id": item.get("intent_id") or item.get("segment_id") or f"seg_{index + 1:03d}",
                    "order": index,
                    "title": item.get("title") or item.get("action") or f"Step {index + 1}",
                    "description": item.get("description") or item.get("detail"),
                    "intent_id": item.get("intent_id"),
                    "intent_tags": list(item.get("intent_tags") or []),
                    "motion_constraint_objects": list(item.get("motion_constraint_objects") or []),
                    "entity_id": item.get("entity_id"),
                    "entity_kind": item.get("entity_kind"),
                    "entity_refs": list(item.get("entity_refs") or []),
                    "anchors": list(item.get("anchors") or []),
                    "metadata": dict(item.get("metadata") or {}),
                    "role": item.get("role"),
                }
            )
    return items


def _extract_consumer_hints(governance: Optional[Dict[str, Any]]) -> list[str]:
    constraints = (governance or {}).get("governance_constraints")
    if not isinstance(constraints, dict):
        return []
    spatial_schedule = constraints.get("spatial_schedule")
    if not isinstance(spatial_schedule, dict):
        return []
    return [str(hint) for hint in list(spatial_schedule.get("consumer_hints") or []) if hint]


def _collect_entities(items: Iterable[dict[str, Any]]) -> list[SpatialEntityRef]:
    entities: dict[str, SpatialEntityRef] = {}
    for item in items:
        entity_id = item.get("entity_id")
        entity_kind = item.get("entity_kind")
        if entity_id and entity_kind and entity_id not in entities:
            entities[entity_id] = SpatialEntityRef(
                entity_id=entity_id,
                entity_kind=entity_kind,
                display_name=item.get("title"),
                role=item.get("role"),
                tags=list(item.get("intent_tags") or []),
                metadata=dict(item.get("metadata") or {}),
            )
        for entity_ref in list(item.get("entity_refs") or []):
            if not isinstance(entity_ref, dict):
                continue
            ref_id = entity_ref.get("entity_id")
            ref_kind = entity_ref.get("entity_kind")
            if ref_id and ref_kind and ref_id not in entities:
                entities[ref_id] = SpatialEntityRef(
                    entity_id=ref_id,
                    entity_kind=ref_kind,
                    display_name=entity_ref.get("display_name"),
                    role=entity_ref.get("role"),
                    tags=list(entity_ref.get("tags") or []),
                    metadata=dict(entity_ref.get("metadata") or {}),
                )
    return list(entities.values())


def _collect_anchors(
    items: Iterable[dict[str, Any]],
    world_context: Optional[Dict[str, Any]],
) -> list[SpatialAnchor]:
    anchors: dict[str, SpatialAnchor] = {}

    if isinstance(world_context, dict):
        scene_id = world_context.get("scene_id")
        if scene_id:
            anchors[str(scene_id)] = SpatialAnchor(
                anchor_id=str(scene_id),
                anchor_kind="scene",
                metadata={"source": "world_memory_packet"},
            )
        current_zone = world_context.get("current_zone")
        if current_zone:
            anchors[str(current_zone)] = SpatialAnchor(
                anchor_id=str(current_zone),
                anchor_kind="zone",
                metadata={"source": "world_memory_packet"},
            )

    for item in items:
        for anchor in list(item.get("anchors") or []):
            if isinstance(anchor, str):
                anchors.setdefault(
                    anchor,
                    SpatialAnchor(anchor_id=anchor),
                )
                continue
            if not isinstance(anchor, dict):
                continue
            anchor_id = anchor.get("anchor_id")
            if anchor_id and anchor_id not in anchors:
                anchors[anchor_id] = SpatialAnchor(
                    anchor_id=anchor_id,
                    anchor_kind=anchor.get("anchor_kind", "logical"),
                    label=anchor.get("label"),
                    metadata=dict(anchor.get("metadata") or {}),
                )

    return list(anchors.values())


def _build_segments(
    items: Iterable[dict[str, Any]],
    anchors: list[SpatialAnchor],
) -> list[SpatialScheduleSegment]:
    default_anchor_ids = [anchor.anchor_id for anchor in anchors]
    segments: list[SpatialScheduleSegment] = []
    for item in items:
        entity_refs = list(item.get("entity_refs") or [])
        if not entity_refs and item.get("entity_id"):
            entity_refs = [item["entity_id"]]

        anchor_ids = []
        for anchor in list(item.get("anchors") or []):
            if isinstance(anchor, str):
                anchor_ids.append(anchor)
            elif isinstance(anchor, dict) and anchor.get("anchor_id"):
                anchor_ids.append(anchor["anchor_id"])
        if not anchor_ids:
            anchor_ids = list(default_anchor_ids)

        segments.append(
            SpatialScheduleSegment(
                segment_id=item["segment_id"],
                order=item["order"],
                title=item["title"],
                description=item.get("description"),
                intent_id=item.get("intent_id"),
                entity_refs=entity_refs,
                intent_tags=list(item.get("intent_tags") or []),
                anchors=anchor_ids,
                motion_constraint_objects=list(item.get("motion_constraint_objects") or []),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return segments


def _build_constraint_summary(
    *,
    items: Iterable[dict[str, Any]],
    governance: Optional[Dict[str, Any]],
    consumer_hints: list[str],
) -> dict[str, Any]:
    motion_constraint_types = []
    for item in items:
        for obj in list(item.get("motion_constraint_objects") or []):
            if not isinstance(obj, dict):
                continue
            obj_type = obj.get("constraint_type") or obj.get("type") or obj.get("kind")
            if obj_type and obj_type not in motion_constraint_types:
                motion_constraint_types.append(str(obj_type))

    summary = {
        "consumer_hints": list(consumer_hints),
        "motion_constraint_types": motion_constraint_types,
    }
    if decision_summary := _derive_schedule_title(decision=None, governance=governance):
        summary["intent_summary"] = decision_summary
    return summary


def _derive_schedule_title(
    *,
    decision: Optional[str],
    governance: Optional[Dict[str, Any]],
) -> Optional[str]:
    if decision:
        return decision.strip()
    goals = list((governance or {}).get("goals") or [])
    if goals:
        return str(goals[0]).strip()
    return None


def _derive_emission_reason(governance: Optional[Dict[str, Any]]) -> str:
    constraints = (governance or {}).get("governance_constraints")
    if isinstance(constraints, dict):
        spatial_schedule = constraints.get("spatial_schedule")
        if isinstance(spatial_schedule, dict) and spatial_schedule.get("requested") is True:
            return "governance_constraints.spatial_schedule.requested"
    for deliverable in list((governance or {}).get("deliverables") or []):
        if not isinstance(deliverable, dict):
            continue
        if deliverable.get("mime_type") == SPATIAL_SCHEDULE_ARTIFACT_MIME:
            return "deliverable.mime_type"
    return "requested_output_type"


def _summarize_operator_prompt(governance: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(governance, dict):
        return None
    human_instructions = governance.get("human_instructions")
    if isinstance(human_instructions, str) and human_instructions.strip():
        return human_instructions.strip()[:280]
    return None


def _extract_world_context_refs(world_context: Optional[Dict[str, Any]]) -> list[str]:
    if not isinstance(world_context, dict):
        return []
    refs = []
    for key in ("snapshot_id", "scene_id", "current_zone"):
        value = world_context.get(key)
        if value:
            refs.append(f"{key}:{value}")
    return refs


def _build_governance_snapshot(governance: Optional[Dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(governance, dict):
        return {}
    return {
        "goals": list(governance.get("goals") or []),
        "requested_output_type": governance.get("requested_output_type"),
        "consumer_hints": _extract_consumer_hints(governance),
    }


def _extract_timebase(
    world_context: Optional[Dict[str, Any]],
    items: Iterable[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    if isinstance(world_context, dict) and isinstance(world_context.get("timebase"), dict):
        return dict(world_context["timebase"])

    for item in items:
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("timebase"), dict):
            return dict(metadata["timebase"])
    return None


def _build_active_schedule_projection(context: Dict[str, Any]) -> Dict[str, Any]:
    consumer_refs = []
    for consumer_code, receipt in dict(context.get("consumer_receipts") or {}).items():
        if not isinstance(receipt, dict):
            continue
        receipt_ref = receipt.get("receipt_ref") or {}
        consumer_refs.append(
            {
                "consumer_code": consumer_code,
                "status": receipt.get("status"),
                "receipt_artifact_id": receipt_ref.get("artifact_id"),
            }
        )

    return {
        "schedule_id": context.get("schedule_id"),
        "status": context.get("status"),
        "entity_kinds": list(context.get("entity_kinds") or []),
        "active_segments": list(context.get("active_segments") or []),
        "consumer_refs": consumer_refs,
        "revision_refs": list(context.get("schedule_revision_refs") or []),
        "updated_at": context.get("updated_at"),
    }


def _build_world_card_schedule_line(context: Dict[str, Any]) -> str:
    active_segments = list(context.get("active_segments") or [])
    if active_segments:
        title = active_segments[0].get("title") or context.get("schedule_id")
    else:
        title = context.get("schedule_id")
    return f"Active schedule: {title}"


def _split_world_card_lines(text: Any) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    return [line for line in text.splitlines() if line.strip()]


__all__ = [
    "SPATIAL_SCHEDULE_ARTIFACT_MIME",
    "SPATIAL_SCHEDULE_COMPILER_VERSION",
    "build_spatial_schedule_artifact",
    "build_spatial_schedule_context",
    "build_spatial_scheduling_ir",
    "emit_spatial_schedule_for_task_ir",
    "persist_spatial_schedule_context_to_session",
    "refresh_world_sidecars",
    "should_emit_spatial_schedule",
    "SPATIAL_SCHEDULING_SCHEMA_VERSION",
]
