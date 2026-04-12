from backend.app.system_capabilities.world_memory_core.services.context_export_facade import (
    ContextExportFacade,
)


def test_world_card_projection_text_includes_zone():
    result = ContextExportFacade().export_context(
        workspace_id="ws-demo",
        receipt={
            "scene_id": "scene.demo",
            "current_zone": "window_side",
            "visible_objects": ["window_light"],
        },
    )

    assert "window_side" in result["world_card_text"]


def test_world_card_projection_text_marks_stale_motion_context():
    result = ContextExportFacade().export_context(
        workspace_id="ws-demo",
        motion_context={
            "motion_id": "motion-stale",
            "provider": "comfyui_kimodo",
            "status": "completed",
            "updated_at": "2026-04-09T00:00:00Z",
            "expires_at": "2026-04-09T01:00:00Z",
            "artifact_refs": [{"artifact_kind": "preview"}],
        },
    )

    assert "Motion context freshness: stale" in result["world_card_text"]
    assert "Motion artifacts ready: preview" in result["world_card_text"]
    assert "Active motion:" not in result["world_card_text"]
    assert (
        result["world_memory_packet"]["metadata"]["motion_stale_reason"] == "expired"
    )


def test_world_card_projection_text_includes_performance_context():
    result = ContextExportFacade().export_context(
        workspace_id="ws-demo",
        performance_context={
            "context_version": "performance_context.v1",
            "performance_mode": "audio_driven_talking_head",
            "execution_bridge": "mms_storyboard_preview",
            "preview_ready_state": "ready",
            "face_lane_active": True,
            "face_source_type": "speaker_audio",
            "body_lane_active": False,
            "body_source_type": "none",
            "retarget_ready_state": "not_applicable",
            "updated_at": "2026-04-10T01:30:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "source_run_id": "perf-run-demo",
        },
    )

    assert "Performance mode: audio_driven_talking_head" in result["world_card_text"]
    assert "Performance preview state: ready" in result["world_card_text"]
    assert "Face lane: active (speaker_audio)" in result["world_card_text"]
    assert "Performance context freshness: fresh" in result["world_card_text"]
    assert (
        result["world_memory_packet"]["metadata"]["performance_execution_bridge"]
        == "mms_storyboard_preview"
    )
