from types import SimpleNamespace

from backend.app.models.handoff import HandoffIn
from backend.app.services.orchestration.meeting._ir_compiler import MeetingIRCompilerMixin
from backend.app.services.orchestration.meeting.spatial_scheduling_compiler import (
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
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
