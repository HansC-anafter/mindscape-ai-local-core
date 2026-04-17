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
    world_anchors = _collect_world_anchors(world_context)
    anchors = _collect_anchors(items, world_anchors)
    entities = _collect_entities(items)
    segments = _build_segments(
        items,
        anchors,
        world_anchor_ids=[anchor.anchor_id for anchor in world_anchors],
    )
    timebase, source_conflicts = _resolve_timebase(
        world_context=world_context,
        items=items,
    )
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
            "timebase": timebase,
            "emission_reason": _derive_emission_reason(governance),
            "compiler_version": SPATIAL_SCHEDULE_COMPILER_VERSION,
            "operator_prompt_summary": _summarize_operator_prompt(governance),
            "world_context_refs": _extract_world_context_refs(world_context),
            "governance_snapshot": _build_governance_snapshot(governance),
            "source_conflicts": source_conflicts,
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
            "uri": artifact.uri,
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
    existing = normalize_spatial_schedule_context(
        session.metadata.get("spatial_schedule_context")
    )
    session.metadata["spatial_schedule_context"] = merge_spatial_schedule_context(
        existing=existing,
        incoming=context,
    )


def refresh_world_sidecars(session: Any, context: Dict[str, Any]) -> None:
    """Project the bounded schedule summary into lightweight world sidecars."""
    from backend.app.system_capabilities.world_memory_core.schema.world_card_projection import (
        WorldCardProjection,
    )
    from backend.app.system_capabilities.world_memory_core.services.world_card_projection_compiler import (
        WorldCardProjectionCompiler,
    )
    from backend.app.system_capabilities.world_memory_core.services.world_state_adapter import (
        WorldStateAdapter,
    )

    if getattr(session, "metadata", None) is None:
        session.metadata = {}
    metadata = session.metadata

    adapter = WorldStateAdapter()
    packet = adapter.build_packet(
        adapter.normalize_receipt(
            workspace_id=str(getattr(session, "workspace_id", "") or ""),
            profile_id=str(metadata.get("profile_id") or ""),
            governance_context=dict(metadata.get("governance_context") or {}),
            spatial_schedule_context=context,
            performance_context=dict(metadata.get("performance_context") or {}),
        )
    )

    existing_world_packet = dict(metadata.get("world_memory_packet") or {})
    existing_world_packet["active_schedule"] = (
        dict(packet.active_schedule) if packet.active_schedule else None
    )
    existing_world_packet["schedule_artifact_refs"] = [
        dict(ref) for ref in packet.schedule_artifact_refs
    ]
    existing_world_packet["schedule_constraints"] = dict(packet.schedule_constraints)
    if packet.performance_state:
        existing_world_packet["performance_state"] = dict(packet.performance_state)
    if packet.metadata:
        existing_world_packet["metadata"] = dict(packet.metadata)
    metadata["world_memory_packet"] = existing_world_packet

    compiler = WorldCardProjectionCompiler()
    generated_projection = compiler.compile(packet)
    existing_projection = dict(metadata.get("world_card_projection") or {})
    existing_summary_lines = [
        line
        for line in list(existing_projection.get("summary_lines") or [])
        if not _is_generated_world_card_summary_line(line)
    ]
    existing_constraints = [
        line
        for line in list(existing_projection.get("constraints") or [])
        if not _is_generated_world_card_constraint(line)
    ]
    merged_projection = WorldCardProjection(
        title=str(existing_projection.get("title") or generated_projection.title),
        summary_lines=existing_summary_lines + list(generated_projection.summary_lines),
        constraints=existing_constraints + list(generated_projection.constraints),
        suggested_focus=list(existing_projection.get("suggested_focus") or []),
        metadata={
            **dict(existing_projection.get("metadata") or {}),
            **dict(generated_projection.metadata),
        },
    )
    metadata["world_card_projection"] = {
        "title": merged_projection.title,
        "summary_lines": list(merged_projection.summary_lines),
        "constraints": list(merged_projection.constraints),
        "suggested_focus": list(merged_projection.suggested_focus),
        "metadata": dict(merged_projection.metadata),
    }
    metadata["world_card_text"] = compiler.render_text(merged_projection)


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
    action_item_records: list[dict[str, Any]] = []
    action_intent_records: list[dict[str, Any]] = []
    if action_intents:
        for index, intent in enumerate(action_intents):
            action_intent_records.append(
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
                    "source_kinds": ["action_intent"],
                }
            )
    for index, item in enumerate(action_items):
        item = dict(item or {})
        action_item_records.append(
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
                "source_kinds": ["action_item"],
            }
        )

    if not action_intent_records:
        return action_item_records

    merged: dict[str, dict[str, Any]] = {
        record["segment_id"]: dict(record)
        for record in action_intent_records
    }
    ordered_segment_ids = [record["segment_id"] for record in action_intent_records]
    for action_item_record in action_item_records:
        segment_id = action_item_record["segment_id"]
        existing = merged.get(segment_id)
        if existing is None:
            merged[segment_id] = dict(action_item_record)
            ordered_segment_ids.append(segment_id)
            continue
        merged[segment_id] = _merge_source_item(
            stronger=existing,
            weaker=action_item_record,
        )
    return [merged[segment_id] for segment_id in ordered_segment_ids]


def _merge_source_item(
    *,
    stronger: dict[str, Any],
    weaker: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(stronger)
    for field in ("title", "description", "intent_id", "entity_id", "entity_kind", "role"):
        if not merged.get(field) and weaker.get(field):
            merged[field] = weaker.get(field)

    merged["intent_tags"] = _merge_unique_strings(
        list(stronger.get("intent_tags") or []),
        list(weaker.get("intent_tags") or []),
    )
    merged["motion_constraint_objects"] = list(
        stronger.get("motion_constraint_objects") or weaker.get("motion_constraint_objects") or []
    )
    merged["entity_refs"] = _merge_entity_refs(
        list(stronger.get("entity_refs") or []),
        list(weaker.get("entity_refs") or []),
    )
    merged["anchors"] = _merge_anchor_payloads(
        list(stronger.get("anchors") or []),
        list(weaker.get("anchors") or []),
    )
    merged["metadata"] = _merge_metadata_dicts(
        stronger=dict(stronger.get("metadata") or {}),
        weaker=dict(weaker.get("metadata") or {}),
    )
    merged["source_kinds"] = _merge_unique_strings(
        list(stronger.get("source_kinds") or []),
        list(weaker.get("source_kinds") or []),
    )
    return merged


def _extract_consumer_hints(governance: Optional[Dict[str, Any]]) -> list[str]:
    hints: list[str] = []

    def _append_hint(raw_hint: Any) -> None:
        hint = str(raw_hint or "").strip()
        if hint and hint not in hints:
            hints.append(hint)

    constraints = (governance or {}).get("governance_constraints")
    if isinstance(constraints, dict):
        spatial_schedule = constraints.get("spatial_schedule")
        if isinstance(spatial_schedule, dict):
            for hint in list(spatial_schedule.get("consumer_hints") or []):
                _append_hint(hint)

    for deliverable in list((governance or {}).get("deliverables") or []):
        if not isinstance(deliverable, dict):
            continue
        for hint in list(deliverable.get("consumer_hints") or []):
            _append_hint(hint)

    return hints


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


def _collect_world_anchors(world_context: Optional[Dict[str, Any]]) -> list[SpatialAnchor]:
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
    return list(anchors.values())


def _collect_anchors(
    items: Iterable[dict[str, Any]],
    world_anchors: list[SpatialAnchor],
) -> list[SpatialAnchor]:
    anchors: dict[str, SpatialAnchor] = {
        anchor.anchor_id: anchor for anchor in list(world_anchors or [])
    }

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
    *,
    world_anchor_ids: list[str],
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
        if world_anchor_ids:
            anchor_ids = _merge_unique_strings(world_anchor_ids, anchor_ids)
        elif not anchor_ids:
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


def _resolve_timebase(
    world_context: Optional[Dict[str, Any]],
    items: Iterable[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    source_conflicts: list[dict[str, Any]] = []
    world_timebase = None
    if isinstance(world_context, dict) and isinstance(world_context.get("timebase"), dict):
        world_timebase = dict(world_context["timebase"])

    for item in items:
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("timebase"), dict):
            item_timebase = dict(metadata["timebase"])
            if world_timebase is not None:
                if item_timebase != world_timebase:
                    source_conflicts.append(
                        {
                            "field": "timebase",
                            "winner": "world_context",
                            "ignored_sources": list(item.get("source_kinds") or []),
                            "segment_id": item.get("segment_id"),
                        }
                    )
                continue
            return item_timebase, source_conflicts
    return world_timebase, source_conflicts


def _merge_unique_strings(primary: list[Any], secondary: list[Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw_value in [*(primary or []), *(secondary or [])]:
        value = str(raw_value or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


def _merge_entity_refs(
    primary: list[Any],
    secondary: list[Any],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_ref in [*(primary or []), *(secondary or [])]:
        if not isinstance(raw_ref, dict):
            continue
        entity_id = str(raw_ref.get("entity_id") or "").strip()
        if not entity_id:
            continue
        if entity_id.lower() in seen:
            continue
        seen.add(entity_id.lower())
        merged.append(dict(raw_ref))
    return merged


def _merge_anchor_payloads(
    primary: list[Any],
    secondary: list[Any],
) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for raw_anchor in [*(primary or []), *(secondary or [])]:
        if isinstance(raw_anchor, str):
            anchor_id = raw_anchor.strip()
            normalized_anchor = anchor_id
        elif isinstance(raw_anchor, dict):
            anchor_id = str(raw_anchor.get("anchor_id") or "").strip()
            normalized_anchor = dict(raw_anchor)
        else:
            continue
        if not anchor_id:
            continue
        key = anchor_id.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized_anchor)
    return merged


def _merge_metadata_dicts(
    *,
    stronger: dict[str, Any],
    weaker: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(weaker)
    merged.update(stronger)
    return merged


def normalize_spatial_schedule_context(
    raw: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    artifact_ref = raw.get("artifact_ref")
    if not isinstance(artifact_ref, dict) or not artifact_ref.get("artifact_id"):
        artifact_ref = _derive_schedule_artifact_ref(raw)

    active_segments = raw.get("active_segments")
    if not isinstance(active_segments, list):
        active_segments = _derive_active_segments(raw)

    consumer_receipts = raw.get("consumer_receipts")
    if not isinstance(consumer_receipts, dict):
        consumer_receipts = _derive_consumer_receipts(raw)

    schedule_revision_refs = raw.get("schedule_revision_refs")
    if not isinstance(schedule_revision_refs, list):
        schedule_revision_refs = _derive_schedule_revision_refs(raw)

    normalized = {
        "schedule_id": raw.get("schedule_id"),
        "schema_version": raw.get("schema_version") or SPATIAL_SCHEDULING_SCHEMA_VERSION,
        "status": raw.get("status") or "planned",
        "artifact_ref": _normalize_artifact_ref(artifact_ref),
        "source_task_id": raw.get("source_task_id"),
        "source_session_id": raw.get("source_session_id"),
        "entity_kinds": _merge_unique_strings(list(raw.get("entity_kinds") or []), []),
        "active_segments": _normalize_active_segments(active_segments),
        "constraint_summary": _normalize_constraint_summary(raw.get("constraint_summary")),
        "schedule_revision_refs": _normalize_schedule_revision_refs(schedule_revision_refs),
        "consumer_receipts": _normalize_consumer_receipts(consumer_receipts),
        "updated_at": raw.get("updated_at"),
    }
    return {
        key: value
        for key, value in normalized.items()
        if value not in (None, {}, [])
    }


def merge_spatial_schedule_context(
    *,
    existing: Optional[Dict[str, Any]],
    incoming: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    normalized_existing = normalize_spatial_schedule_context(existing)
    normalized_incoming = normalize_spatial_schedule_context(incoming)
    if normalized_incoming is None:
        return normalized_existing
    if normalized_existing is None:
        return normalized_incoming

    existing_schedule_id = normalized_existing.get("schedule_id")
    incoming_schedule_id = normalized_incoming.get("schedule_id")
    if existing_schedule_id and existing_schedule_id == incoming_schedule_id:
        merged = dict(normalized_existing)
        merged.update(
            {
                "schedule_id": incoming_schedule_id,
                "schema_version": normalized_incoming.get("schema_version")
                or normalized_existing.get("schema_version"),
                "status": normalized_incoming.get("status")
                or normalized_existing.get("status"),
                "artifact_ref": normalized_incoming.get("artifact_ref")
                or normalized_existing.get("artifact_ref"),
                "source_task_id": normalized_incoming.get("source_task_id")
                or normalized_existing.get("source_task_id"),
                "source_session_id": normalized_incoming.get("source_session_id")
                or normalized_existing.get("source_session_id"),
                "entity_kinds": _merge_unique_strings(
                    list(normalized_existing.get("entity_kinds") or []),
                    list(normalized_incoming.get("entity_kinds") or []),
                ),
                "active_segments": list(
                    normalized_incoming.get("active_segments")
                    or normalized_existing.get("active_segments")
                    or []
                ),
                "constraint_summary": _merge_constraint_summary(
                    existing=normalized_existing.get("constraint_summary"),
                    incoming=normalized_incoming.get("constraint_summary"),
                ),
                "schedule_revision_refs": _merge_schedule_revision_refs(
                    list(normalized_existing.get("schedule_revision_refs") or []),
                    list(normalized_incoming.get("schedule_revision_refs") or []),
                ),
                "consumer_receipts": _merge_consumer_receipts(
                    existing=normalized_existing.get("consumer_receipts"),
                    incoming=normalized_incoming.get("consumer_receipts"),
                ),
                "updated_at": _select_newest_updated_at(
                    normalized_existing.get("updated_at"),
                    normalized_incoming.get("updated_at"),
                ),
            }
        )
        return {
            key: value
            for key, value in merged.items()
            if value not in (None, {}, [])
        }

    merged = dict(normalized_incoming)
    merged["schedule_revision_refs"] = _merge_schedule_revision_refs(
        list(normalized_existing.get("schedule_revision_refs") or []),
        [
            _build_schedule_revision_ref(normalized_existing),
            *list(normalized_incoming.get("schedule_revision_refs") or []),
        ],
    )
    return {
        key: value
        for key, value in merged.items()
        if value not in (None, {}, [])
    }


def _derive_schedule_artifact_ref(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    artifact_ref = raw.get("artifact_ref")
    if isinstance(artifact_ref, dict) and artifact_ref.get("artifact_id"):
        return _normalize_artifact_ref(artifact_ref)

    source_artifact_id = raw.get("source_artifact_id")
    if source_artifact_id:
        return {
            "artifact_id": source_artifact_id,
            "type": raw.get("artifact_type")
            or "application/vnd.mindscape.spatial-scheduling+json",
            "uri": raw.get("artifact_uri"),
        }

    artifact_refs = list(raw.get("artifact_refs") or [])
    for artifact_ref in artifact_refs:
        if isinstance(artifact_ref, dict) and artifact_ref.get("artifact_id"):
            return _normalize_artifact_ref(artifact_ref)
    return None


def _derive_active_segments(raw: Dict[str, Any]) -> list[Dict[str, Any]]:
    segment_ids = list(raw.get("active_segment_ids") or [])
    segments = []
    for segment_id in segment_ids:
        normalized_segment_id = str(segment_id or "").strip()
        if not normalized_segment_id:
            continue
        segments.append(
            {
                "segment_id": normalized_segment_id,
                "title": normalized_segment_id,
                "entity_refs": [],
                "anchor_ids": [],
            }
        )
    return segments


def _derive_consumer_receipts(raw: Dict[str, Any]) -> Dict[str, Any]:
    receipts: Dict[str, Any] = {}
    for consumer_ref in list(raw.get("consumer_refs") or []):
        if not isinstance(consumer_ref, dict):
            continue
        consumer_code = str(consumer_ref.get("consumer_code") or "").strip()
        if not consumer_code:
            continue
        receipts[consumer_code] = {
            "status": consumer_ref.get("status"),
            "receipt_ref": {
                "artifact_id": consumer_ref.get("receipt_artifact_id"),
            },
        }
    return receipts


def _derive_schedule_revision_refs(raw: Dict[str, Any]) -> list[Dict[str, Any]]:
    revisions = []
    for revision_ref in list(raw.get("revision_refs") or []):
        if not isinstance(revision_ref, dict):
            continue
        normalized = _normalize_schedule_revision_ref(revision_ref)
        if normalized is not None:
            revisions.append(normalized)
    return revisions


def _normalize_artifact_ref(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    artifact_id = str(raw.get("artifact_id") or "").strip()
    if not artifact_id:
        return None

    normalized = {
        "artifact_id": artifact_id,
        "type": raw.get("type") or raw.get("artifact_type"),
        "uri": raw.get("uri"),
    }
    return {
        key: value
        for key, value in normalized.items()
        if value not in (None, "", [], {})
    }


def _normalize_active_segments(raw_segments: Any) -> list[Dict[str, Any]]:
    normalized_segments: list[Dict[str, Any]] = []
    for raw_segment in list(raw_segments or []):
        if not isinstance(raw_segment, dict):
            continue
        segment_id = str(raw_segment.get("segment_id") or "").strip()
        if not segment_id:
            continue
        normalized_segments.append(
            {
                "segment_id": segment_id,
                "title": raw_segment.get("title") or segment_id,
                "entity_refs": _merge_unique_strings(
                    list(raw_segment.get("entity_refs") or []),
                    [],
                ),
                "anchor_ids": _merge_unique_strings(
                    list(raw_segment.get("anchor_ids") or raw_segment.get("anchors") or []),
                    [],
                ),
            }
        )
    return normalized_segments


def _normalize_constraint_summary(raw_summary: Any) -> Dict[str, Any]:
    if not isinstance(raw_summary, dict):
        return {}

    normalized: Dict[str, Any] = {}
    for key, value in raw_summary.items():
        if isinstance(value, list):
            normalized[key] = _merge_unique_strings(list(value), [])
        elif value not in (None, {}, []):
            normalized[key] = value
    return normalized


def _normalize_schedule_revision_refs(raw_revisions: Any) -> list[Dict[str, Any]]:
    normalized_revisions: list[Dict[str, Any]] = []
    for raw_revision in list(raw_revisions or []):
        normalized = _normalize_schedule_revision_ref(raw_revision)
        if normalized is not None:
            normalized_revisions.append(normalized)
    return normalized_revisions


def _normalize_schedule_revision_ref(raw_revision: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_revision, dict):
        return None
    schedule_id = str(raw_revision.get("schedule_id") or "").strip()
    if not schedule_id:
        return None

    artifact_ref = _normalize_artifact_ref(raw_revision.get("artifact_ref"))
    if artifact_ref is None:
        artifact_ref = _normalize_artifact_ref(
            {
                "artifact_id": raw_revision.get("artifact_id"),
                "artifact_type": raw_revision.get("artifact_type")
                or raw_revision.get("type"),
                "uri": raw_revision.get("uri"),
            }
        )

    normalized = {
        "schedule_id": schedule_id,
        "relation": raw_revision.get("relation")
        or raw_revision.get("relationship")
        or "supersedes",
        "artifact_ref": artifact_ref,
        "updated_at": raw_revision.get("updated_at"),
    }
    return {
        key: value
        for key, value in normalized.items()
        if value not in (None, "", [], {})
    }


def _normalize_consumer_receipts(raw_receipts: Any) -> Dict[str, Any]:
    normalized_receipts: Dict[str, Any] = {}
    if not isinstance(raw_receipts, dict):
        return normalized_receipts

    for consumer_code, raw_receipt in raw_receipts.items():
        normalized_consumer_code = str(consumer_code or "").strip()
        if not normalized_consumer_code or not isinstance(raw_receipt, dict):
            continue
        normalized_receipt = {
            "status": raw_receipt.get("status"),
            "receipt_ref": _normalize_artifact_ref(raw_receipt.get("receipt_ref")),
        }
        normalized_receipts[normalized_consumer_code] = {
            key: value
            for key, value in normalized_receipt.items()
            if value not in (None, "", [], {})
        }
    return normalized_receipts


def _merge_constraint_summary(
    *,
    existing: Any,
    incoming: Any,
) -> Dict[str, Any]:
    merged = _normalize_constraint_summary(existing)
    for key, value in _normalize_constraint_summary(incoming).items():
        if isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _merge_unique_strings(list(merged.get(key) or []), value)
        else:
            merged[key] = value
    return merged


def _merge_consumer_receipts(
    *,
    existing: Any,
    incoming: Any,
) -> Dict[str, Any]:
    merged = _normalize_consumer_receipts(existing)
    for consumer_code, incoming_receipt in _normalize_consumer_receipts(incoming).items():
        current_receipt = dict(merged.get(consumer_code) or {})
        current_receipt.update(incoming_receipt)
        merged[consumer_code] = current_receipt
    return merged


def _merge_schedule_revision_refs(
    primary: list[Dict[str, Any]],
    secondary: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    merged: list[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for revision_ref in [*(primary or []), *(secondary or [])]:
        normalized = _normalize_schedule_revision_ref(revision_ref)
        if normalized is None:
            continue
        key = (
            str(normalized.get("schedule_id") or "").lower(),
            str(normalized.get("relation") or "supersedes").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    return merged


def _build_schedule_revision_ref(context: Dict[str, Any]) -> Dict[str, Any]:
    revision_ref = {
        "schedule_id": context.get("schedule_id"),
        "relation": "supersedes",
        "artifact_ref": context.get("artifact_ref"),
        "updated_at": context.get("updated_at"),
    }
    return {
        key: value
        for key, value in revision_ref.items()
        if value not in (None, "", [], {})
    }


def _select_newest_updated_at(
    existing_updated_at: Any,
    incoming_updated_at: Any,
) -> Optional[str]:
    parsed_existing = _parse_updated_at(existing_updated_at)
    parsed_incoming = _parse_updated_at(incoming_updated_at)
    if parsed_existing and parsed_incoming:
        return incoming_updated_at if parsed_incoming >= parsed_existing else existing_updated_at
    if parsed_incoming:
        return incoming_updated_at
    if parsed_existing:
        return existing_updated_at
    return incoming_updated_at or existing_updated_at


def _parse_updated_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _is_generated_world_card_summary_line(line: Any) -> bool:
    text = str(line or "").strip()
    return text.startswith(
        (
            "Active schedule:",
            "Performance mode:",
            "Performance preview state:",
            "Face lane:",
            "Body lane:",
            "Performance context freshness:",
        )
    )


def _is_generated_world_card_constraint(line: Any) -> bool:
    text = str(line or "").strip()
    return text.startswith(("schedule_", "performance_"))


__all__ = [
    "SPATIAL_SCHEDULE_ARTIFACT_MIME",
    "SPATIAL_SCHEDULE_COMPILER_VERSION",
    "build_spatial_schedule_artifact",
    "build_spatial_schedule_context",
    "build_spatial_scheduling_ir",
    "emit_spatial_schedule_for_task_ir",
    "merge_spatial_schedule_context",
    "normalize_spatial_schedule_context",
    "persist_spatial_schedule_context_to_session",
    "refresh_world_sidecars",
    "should_emit_spatial_schedule",
    "SPATIAL_SCHEDULING_SCHEMA_VERSION",
]
