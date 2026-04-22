from types import SimpleNamespace

from backend.app.models.handoff import HandoffIn
from backend.app.services.orchestration.meeting._ir_compiler import MeetingIRCompilerMixin
from backend.app.services.orchestration.meeting.spatial_scheduling_compiler import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    build_spatial_schedule_artifact,
    build_spatial_schedule_context,
    build_spatial_scheduling_ir,
    persist_spatial_schedule_context_to_session,
)


class _FakeMeeting(MeetingIRCompilerMixin):
    def __init__(self) -> None:
        self.profile_id = "profile-001"
        self.session = SimpleNamespace(
            id="session-001",
            workspace_id="ws-001",
            project_id="proj-001",
            metadata={
                "governance_context": {"workspace_id": "ws-001", "mode": "director"},
                "memory_packet": {"selection": {"workspace_mode": "director"}},
                "world_memory_packet": {
                    "snapshot_id": "snap-001",
                    "source": "synthetic",
                    "scene_id": "scene.demo",
                    "current_zone": "main_floor",
                },
                "world_card_projection": {
                    "title": "World Card",
                    "summary_lines": ["Scene: scene.demo", "Zone: main_floor"],
                    "constraints": [],
                    "suggested_focus": [],
                    "metadata": {"source": "synthetic"},
                },
                "world_card_text": "World Card\n- Scene: scene.demo\n- Zone: main_floor",
            },
        )


def test_compile_to_task_ir_emits_spatial_schedule_artifact_and_session_sidecars():
    meeting = _FakeMeeting()
    handoff = HandoffIn(
        handoff_id="handoff-001",
        workspace_id="ws-001",
        intent_summary="Block actor movement on stage",
        goals=["Plan a short staged actor movement"],
        governance_constraints={
            "spatial_schedule": {
                "requested": True,
                "consumer_hints": ["performance_direction"],
            }
        },
    )

    task_ir = meeting._compile_to_task_ir(
        decision="Actor enters frame and lands on the stage mark.",
        action_items=[
            {
                "intent_id": "intent-001",
                "title": "Enter frame",
                "description": "Primary actor walks to stage mark.",
                "entity_id": "actor.main",
                "entity_kind": "actor",
                "intent_tags": ["performance", "blocking"],
            }
        ],
        handoff_in=handoff,
    )

    assert len(task_ir.artifacts) == 1
    artifact = task_ir.artifacts[0]
    assert artifact.type == SPATIAL_SCHEDULE_ARTIFACT_MIME
    assert artifact.metadata["content_json"]["segments"][0]["title"] == "Enter frame"
    assert artifact.metadata["content_json"]["entities"][0]["entity_kind"] == "actor"

    spatial_schedule_context = meeting.session.metadata["spatial_schedule_context"]
    assert spatial_schedule_context["schedule_id"] == artifact.metadata["schedule_id"]
    assert (
        meeting.session.metadata["world_memory_packet"]["active_schedule"]["schedule_id"]
        == artifact.metadata["schedule_id"]
    )
    assert "Active schedule:" in meeting.session.metadata["world_card_text"]


def test_compile_to_task_ir_projects_schedule_via_world_memory_core_and_preserves_world_card_context():
    meeting = _FakeMeeting()
    meeting.session.metadata["profile_id"] = "profile-001"
    meeting.session.metadata["performance_context"] = {
        "context_version": "performance_context.v1",
        "storyboard_id": "sb-demo",
        "scene_id": "scene.demo",
        "performance_mode": "audio_driven_talking_head",
        "execution_bridge": "mms_storyboard_preview",
        "preview_ready_state": "ready",
        "face_lane_active": True,
        "face_source_type": "speaker_audio",
        "body_lane_active": False,
        "body_source_type": "motion_context",
        "retarget_ready_state": "ready",
        "updated_at": "2026-04-16T12:10:00+00:00",
        "expires_at": "2099-01-01T00:00:00Z",
        "source_run_id": "perf-run-demo",
    }
    handoff = HandoffIn(
        handoff_id="handoff-001b",
        workspace_id="ws-001",
        intent_summary="Block actor movement on stage with performance context",
        goals=["Plan a staged actor movement"],
        governance_constraints={
            "spatial_schedule": {
                "requested": True,
                "consumer_hints": ["performance_direction"],
            }
        },
    )

    meeting._compile_to_task_ir(
        decision="Actor enters frame and lands on the stage mark.",
        action_items=[
            {
                "intent_id": "intent-001b",
                "title": "Enter frame",
                "description": "Primary actor walks to stage mark.",
                "entity_id": "actor.main",
                "entity_kind": "actor",
                "intent_tags": ["performance", "blocking"],
            }
        ],
        handoff_in=handoff,
    )

    world_packet = meeting.session.metadata["world_memory_packet"]
    assert world_packet["active_schedule"]["title"] == "Enter frame"
    assert world_packet["performance_state"]["performance_mode"] == "audio_driven_talking_head"
    assert world_packet["metadata"]["performance_freshness"] == "fresh"

    projection = meeting.session.metadata["world_card_projection"]
    assert "Scene: scene.demo" in projection["summary_lines"]
    assert "Zone: main_floor" in projection["summary_lines"]
    assert "Active schedule: Enter frame" in projection["summary_lines"]
    assert "Performance mode: audio_driven_talking_head" in projection["summary_lines"]
    assert any(
        constraint.startswith("schedule_scene=") for constraint in projection["constraints"]
    )
    assert any(
        "Plan a staged actor movement" in constraint for constraint in projection["constraints"]
    )
    assert "performance_execution_bridge=mms_storyboard_preview" in projection["constraints"]
    assert "Performance run: perf-run-demo" in meeting.session.metadata["world_card_text"]


def test_compile_to_task_ir_does_not_emit_spatial_schedule_for_markdown_only_requests():
    meeting = _FakeMeeting()
    handoff = HandoffIn(
        handoff_id="handoff-002",
        workspace_id="ws-001",
        intent_summary="Write markdown summary only",
        goals=["Produce a markdown summary"],
        requested_output_type="text/markdown",
    )

    task_ir = meeting._compile_to_task_ir(
        decision="Summarize the work in markdown.",
        action_items=[{"title": "Write summary", "description": "Produce markdown only."}],
        handoff_in=handoff,
    )

    assert task_ir.artifacts == []
    assert "spatial_schedule_context" not in meeting.session.metadata


def test_compile_to_task_ir_emits_spatial_schedule_from_deliverable_mime():
    meeting = _FakeMeeting()
    handoff = HandoffIn(
        handoff_id="handoff-003",
        workspace_id="ws-001",
        intent_summary="Return a neutral spatial schedule artifact",
        deliverables=[
            {
                "name": "Spatial schedule",
                "mime_type": SPATIAL_SCHEDULE_ARTIFACT_MIME,
            }
        ],
    )

    task_ir = meeting._compile_to_task_ir(
        decision="Camera tracks the actor to the stage mark.",
        action_items=[
            {
                "title": "Track actor",
                "description": "Camera follows the actor to the mark.",
                "entity_id": "camera.main",
                "entity_kind": "camera",
            }
        ],
        handoff_in=handoff,
    )

    assert len(task_ir.artifacts) == 1
    assert task_ir.artifacts[0].type == SPATIAL_SCHEDULE_ARTIFACT_MIME


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
    ]
    assert [anchor.anchor_id for anchor in schedule.anchors] == [
        "scene.demo",
        "main_floor",
        "stage_mark",
    ]
    assert schedule.segments[0].anchors == ["scene.demo", "main_floor", "stage_mark"]
    summary = schedule.constraint_summary.model_dump(mode="json")
    assert "single_stage_scene" in [item["summary"] for item in summary["scene"]]
    assert "single_camera_family" in summary["camera"][0]["summary"]
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


def test_build_spatial_scheduling_ir_reflects_governance_object_and_anchor_identity_in_segments():
    schedule = build_spatial_scheduling_ir(
        task_id="task-governance-objects-001",
        workspace_id="ws-001",
        session_id="session-001",
        decision="Counter tray proof lane",
        action_items=[
            {
                "intent_id": "seg-001",
                "title": "切分空間段落並標記作用中物件與錨點",
                "description": "Mark the bounded object and anchor set for the proof lane.",
            },
            {
                "intent_id": "seg-002",
                "title": "產出 world proof lane 可消費的空間排程",
                "description": "Emit the bounded world-proof schedule.",
            },
        ],
        action_intents=None,
        governance={
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": True,
                    "consumer_hints": ["video_renderer", "ue5_runtime"],
                    "bounded_constraints": {
                        "camera": {
                            "entity_ids": ["camera.main"],
                            "must_hold": ["single_viewpoint"],
                        },
                        "objects": [
                            {
                                "entity_id": "object.counter",
                                "role": "support_surface",
                                "label": "Counter",
                            },
                            {
                                "entity_id": "object.tray",
                                "role": "primary_prop",
                                "label": "Tray",
                            },
                        ],
                        "anchors": [
                            {
                                "anchor_id": "anchor.counter",
                                "anchor_kind": "surface",
                                "label": "Counter surface",
                            },
                            {
                                "anchor_id": "anchor.tray_rest",
                                "anchor_kind": "placement",
                                "label": "Tray rest",
                            },
                        ],
                        "spatial_relations": [
                            {
                                "relation": "tray_on_counter",
                                "source_entity_id": "object.tray",
                                "target_anchor_id": "anchor.counter",
                            }
                        ],
                    },
                }
            }
        },
        world_context=None,
    )

    assert sorted(entity.entity_id for entity in schedule.entities) == [
        "camera.main",
        "object.counter",
        "object.tray",
    ]
    assert sorted(anchor.anchor_id for anchor in schedule.anchors) == [
        "anchor.counter",
        "anchor.tray_rest",
    ]
    assert sorted(schedule.segments[0].entity_refs) == [
        "camera.main",
        "object.counter",
        "object.tray",
    ]
    assert sorted(schedule.segments[0].anchors) == [
        "anchor.counter",
        "anchor.tray_rest",
    ]
    assert sorted(schedule.segments[1].entity_refs) == [
        "camera.main",
        "object.counter",
        "object.tray",
    ]
    assert sorted(schedule.segments[1].anchors) == [
        "anchor.counter",
        "anchor.tray_rest",
    ]


def test_persist_spatial_schedule_context_to_session_merges_same_schedule_receipts():
    session = SimpleNamespace(
        metadata={
            "spatial_schedule_context": {
                "schedule_id": "ssched_same",
                "schema_version": "2026-04-16",
                "artifact_ref": {"artifact_id": "task-old/spatial_schedule"},
                "active_segments": [
                    {
                        "segment_id": "seg_old",
                        "title": "Old segment",
                        "entity_refs": ["actor.old"],
                        "anchor_ids": ["zone.old"],
                    }
                ],
                "constraint_summary": {
                    "consumer_hints": ["performance_direction"],
                    "consumer_prompt_bindings": [
                        {
                            "consumer": "performance_direction",
                            "section_key": "scene",
                            "text": "Preserve the original stage layout.",
                            "anchor_ids": ["zone.old"],
                        }
                    ],
                },
                "consumer_receipts": {
                    "motion_runtime": {
                        "status": "completed",
                        "receipt_ref": {"artifact_id": "motion-receipt-001"},
                    }
                },
                "updated_at": "2026-04-16T10:00:00+00:00",
            }
        }
    )

    persist_spatial_schedule_context_to_session(
        session,
        {
            "schedule_id": "ssched_same",
            "schema_version": "2026-04-16",
            "artifact_ref": {"artifact_id": "task-old/spatial_schedule"},
            "active_segments": [
                {
                    "segment_id": "seg_new",
                    "title": "New segment window",
                    "entity_refs": ["actor.lead"],
                    "anchor_ids": ["zone.stage"],
                }
            ],
            "constraint_summary": {
                "consumer_hints": ["motion_runtime"],
                "consumer_prompt_bindings": [
                    {
                        "consumer": "motion_runtime",
                        "section_key": "camera",
                        "text": "Follow the new stage window segment.",
                        "anchor_ids": ["zone.stage"],
                    }
                ],
            },
            "consumer_receipts": {
                "performance_direction": {
                    "status": "compiled",
                    "receipt_ref": {"artifact_id": "pd-storyboard-001"},
                }
            },
            "updated_at": "2026-04-16T12:00:00+00:00",
        },
    )

    context = session.metadata["spatial_schedule_context"]
    assert context["schedule_id"] == "ssched_same"
    assert context["active_segments"][0]["segment_id"] == "seg_new"
    assert context["consumer_receipts"]["motion_runtime"]["receipt_ref"]["artifact_id"] == (
        "motion-receipt-001"
    )
    assert (
        context["consumer_receipts"]["performance_direction"]["receipt_ref"]["artifact_id"]
        == "pd-storyboard-001"
    )
    assert context["constraint_summary"]["consumer_hints"] == [
        "performance_direction",
        "motion_runtime",
    ]
    assert len(context["constraint_summary"]["consumer_prompt_bindings"]) == 2
    assert context["updated_at"] == "2026-04-16T12:00:00+00:00"


def test_build_spatial_schedule_context_serializes_constraint_summary_items():
    schedule = build_spatial_scheduling_ir(
        task_id="task-serialize-001",
        workspace_id="ws-001",
        session_id="session-001",
        decision="Bounded counter tray execution",
        action_items=[
            {
                "title": "切分空間段落並標記作用中物件與錨點",
                "description": "標記 counter/tray 的 bounded 空間關係。",
            }
        ],
        governance={
            "governance_constraints": {
                "spatial_schedule": {
                    "requested": True,
                    "consumer_hints": ["ue5_runtime"],
                    "bounded_constraints": {
                        "objects": [
                            {"entity_id": "object.counter", "role": "support_surface"},
                            {"entity_id": "object.tray", "role": "primary_prop"},
                        ],
                        "anchors": [
                            {"anchor_id": "anchor.counter", "anchor_kind": "surface"},
                            {"anchor_id": "anchor.tray_rest", "anchor_kind": "placement"},
                        ],
                    },
                }
            }
        },
    )

    artifact = build_spatial_schedule_artifact(
        task_id="task-serialize-001",
        schedule=schedule,
    )
    context = build_spatial_schedule_context(schedule=schedule, artifact=artifact)

    assert context["constraint_summary"]["consumer_hints"] == ["ue5_runtime"]
    assert context["constraint_summary"]["objects"][0]["entity_refs"] == [
        "object.counter"
    ]
    assert context["constraint_summary"]["objects"][1]["entity_refs"] == [
        "object.tray"
    ]
