from spatial_scheduling_compiler_test_support import (
    HandoffIn,
    SPATIAL_SCHEDULE_ARTIFACT_MIME,
    _FakeMeeting,
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
