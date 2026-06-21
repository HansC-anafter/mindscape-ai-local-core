from types import SimpleNamespace

from spatial_scheduling_compiler_test_support import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    build_governance_object_schedule,
    build_native_camera_handoff_schedule_context,
    build_spatial_scheduling_ir,
)


def test_build_spatial_scheduling_ir_merges_action_item_fallbacks_and_world_context_precedence():
    intent = SimpleNamespace(
        intent_id="intent-merge-001",
        title="Block the lead",
        description="Typed intent owns the segment title.",
        intent_tags=["performance"],
        motion_constraint_objects=[],
        entity_id=None,
        entity_kind=None,
        entity_refs=[],
        anchors=[],
        metadata={"timebase": {"fps": 24, "clock": "intent"}},
    )

    schedule = build_spatial_scheduling_ir(
        task_id="task-merge-001",
        workspace_id="ws-001",
        session_id="session-001",
        decision="Lead lands on the stage mark under the main camera.",
        action_items=[
            {
                "intent_id": "intent-merge-001",
                "title": "Fallback item title",
                "description": "Fallback item fills entity and anchor gaps.",
                "entity_id": "actor.lead",
                "entity_kind": "actor",
                "anchors": [
                    {"anchor_id": "stage_mark", "anchor_kind": "mark", "label": "Stage mark"}
                ],
                "metadata": {"timebase": {"fps": 12, "clock": "item"}},
            }
        ],
        action_intents=[intent],
        governance={
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": True,
                    "consumer_hints": ["performance_direction"],
                    "bounded_constraints": {
                        "scene": {
                            "scene_scope": "single_stage_scene",
                        },
                        "camera": {
                            "must_hold": ["single_camera_family"],
                        },
                        "objects": [
                            {
                                "entity_id": "prop.marker",
                                "role": "target_mark",
                            }
                        ],
                        "anchors": [
                            {
                                "anchor_id": "stage_mark",
                                "anchor_kind": "mark",
                            }
                        ],
                        "spatial_relations": [
                            {
                                "relation": "actor_on_mark",
                                "target_anchor_id": "stage_mark",
                            }
                        ],
                        "occlusion": [
                            {
                                "subject": "actor.lead",
                                "policy": "keep_visible",
                            }
                        ],
                        "displacement": [
                            {
                                "subject_entity_id": "actor.lead",
                                "to_anchor_id": "stage_mark",
                            }
                        ],
                        "output_boundaries": {
                            "scene_count_max": 1,
                        },
                    },
                    "consumer_prompt_bindings": [
                        {
                            "consumer": "performance_direction",
                            "section_key": "scene",
                            "text": "Keep the lead bounded to the stage scene.",
                            "anchor_ids": ["stage_mark"],
                        },
                        {
                            "consumer": "motion_runtime",
                            "section_key": "camera",
                            "text": "Retain the stage-mark framing while the lead lands.",
                            "segment_id": "intent-merge-001",
                            "anchor_ids": ["stage_mark"],
                        },
                    ],
                }
            },
            "deliverables": [
                {
                    "mime_type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
                    "consumer_hints": ["motion_runtime", "performance_direction"],
                }
            ],
        },
        world_context={
            "snapshot_id": "snap-001",
            "scene_id": "scene.demo",
            "current_zone": "main_floor",
            "timebase": {"fps": 30, "clock": "world"},
        },
    )

    assert schedule.consumer_hints == ["performance_direction", "motion_runtime"]
    assert schedule.metadata["timebase"] == {"fps": 30, "clock": "world"}
    assert schedule.metadata["source_conflicts"] == [
        {
            "field": "timebase",
            "winner": "world_context",
            "ignored_sources": ["action_intent", "action_item"],
            "segment_id": "intent-merge-001",
        }
    ]
    assert [entity.entity_id for entity in schedule.entities] == [
        "actor.lead",
        "prop.marker",
        "camera.main",
    ]
    assert [anchor.anchor_id for anchor in schedule.anchors] == [
        "scene.demo",
        "main_floor",
        "stage_mark",
    ]
    assert schedule.segments[0].anchors == ["scene.demo", "main_floor", "stage_mark"]
    summary = schedule.constraint_summary.model_dump(mode="json")
    assert "single_stage_scene" in [item["summary"] for item in summary["scene"]]
    assert any("single_camera_family" in item["summary"] for item in summary["camera"])
    assert summary["objects"][0]["item_id"] == "prop.marker"
    assert summary["anchors"][-1]["item_id"] == "stage_mark"
    assert summary["spatial_relations"][0]["summary"] == "actor_on_mark"
    assert summary["occlusion"][0]["summary"] == "keep_visible"
    assert summary["displacement"][0]["anchor_ids"] == ["stage_mark"]
    assert any(
        "scene_count_max" in item["summary"] for item in summary["output_boundaries"]
    )
    assert schedule.segments[0].consumer_prompt_segments[0].consumer == "performance_direction"
    assert schedule.segments[0].consumer_prompt_segments[1].section_keys == ["camera"]


def test_build_spatial_scheduling_ir_uses_action_item_timebase_when_world_context_absent():
    schedule = build_spatial_scheduling_ir(
        task_id="task-merge-002",
        workspace_id="ws-001",
        session_id="session-001",
        decision="Camera pushes through the hallway.",
        action_items=[
            {
                "intent_id": "intent-merge-002",
                "title": "Push camera",
                "entity_id": "camera.main",
                "entity_kind": "camera",
                "metadata": {"timebase": {"fps": 25, "clock": "item"}},
            }
        ],
        action_intents=[
            SimpleNamespace(
                intent_id="intent-merge-002",
                title="Push camera",
                description="Typed intent without timebase metadata.",
                intent_tags=["camera"],
                motion_constraint_objects=[],
                entity_id="camera.main",
                entity_kind="camera",
                entity_refs=[],
                anchors=[],
                metadata={},
            )
        ],
        governance=None,
        world_context=None,
    )

    assert schedule.metadata["timebase"] == {"fps": 25, "clock": "item"}
    assert schedule.metadata["source_conflicts"] == []


def test_build_spatial_scheduling_ir_includes_governance_and_native_inference_identity_in_segments():
    schedule = build_governance_object_schedule()

    entity_ids = {entity.entity_id for entity in schedule.entities}
    assert {"camera.main", "object.counter", "object.tray"}.issubset(entity_ids)
    assert {"surface.primary", "object.primary"}.issubset(entity_ids)

    anchor_ids = {anchor.anchor_id for anchor in schedule.anchors}
    assert {"anchor.counter", "anchor.tray_rest"}.issubset(anchor_ids)
    assert {"anchor.target_surface", "anchor.object_rest"}.issubset(anchor_ids)

    expected_segment_entities = {
        "camera.main",
        "object.counter",
        "object.tray",
        "surface.primary",
        "object.primary",
    }
    expected_segment_anchors = {
        "anchor.counter",
        "anchor.tray_rest",
        "anchor.target_surface",
        "anchor.object_rest",
    }
    for segment in schedule.segments:
        assert expected_segment_entities.issubset(set(segment.entity_refs))
        assert expected_segment_anchors.issubset(set(segment.anchors))


def test_build_spatial_scheduling_ir_emits_canonical_native_camera_handoff_anchors():
    schedule, context = build_native_camera_handoff_schedule_context()

    native_execution_plan = context["constraint_summary"]["native_execution_plan"]
    camera_blocking = native_execution_plan["camera_blocking"][0]
    assert camera_blocking["camera_entity_id"] == "camera.main"
    assert camera_blocking["mode"] == "hold_then_minor_reframe"
    assert camera_blocking["anchor_ids"] == [
        "anchor.target_surface",
        "anchor.object_rest",
    ]

    blocking_path = native_execution_plan["blocking_paths"][0]
    assert blocking_path["from_anchor_id"] == "anchor.entry_handoff"
    assert blocking_path["to_anchor_id"] == "anchor.object_rest"

    performance_beat = native_execution_plan["performance_beats"][0]
    assert performance_beat["from_anchor_id"] == "anchor.entry_handoff"
    assert performance_beat["to_anchor_id"] == "anchor.object_rest"
    assert "anchor.entry_handoff" in {anchor.anchor_id for anchor in schedule.anchors}
