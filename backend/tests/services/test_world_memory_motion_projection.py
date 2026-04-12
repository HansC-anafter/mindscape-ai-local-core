from backend.app.system_capabilities.world_memory_core.services.world_card_projection_compiler import (
    WorldCardProjectionCompiler,
)
from backend.app.system_capabilities.world_memory_core.services.world_state_adapter import (
    WorldStateAdapter,
)


def test_world_memory_core_projects_motion_context_into_packet_and_world_card():
    motion_context = {
        "motion_id": "motion_demo",
        "provider": "comfyui_kimodo",
        "source_family": "text_to_motion",
        "status": "completed",
        "duration_sec": 4.0,
        "fps": 30,
        "skeleton_family": "soma",
        "skeleton_version": "77j_v1",
        "coordinate_space": "y_up",
        "retarget_profile": "ue5_mannequin",
        "artifact_refs": [
            {
                "artifact_kind": "preview",
                "format": "mp4",
                "storage_key": "motion/demo/preview.mp4",
                "skeleton_family": "soma",
                "skeleton_version": "77j_v1",
                "coordinate_space": "y_up",
            }
        ],
        "motion_constraints": {
            "timing_policy": {"fps": 30},
            "retarget_profile": "ue5_mannequin",
            "constraint_types": ["root2d", "left-hand"],
            "constraint_frame_count_by_type": {"root2d": 3, "left-hand": 2},
            "uses_end_effector_constraints": True,
            "root_path_mode": "dense_path",
        },
    }

    snapshot = WorldStateAdapter().normalize_receipt(
        workspace_id="ws_demo",
        profile_id="profile_demo",
        governance_context={"mode": "presentation"},
        motion_context=motion_context,
    )
    packet = WorldStateAdapter().build_packet(snapshot)
    projection = WorldCardProjectionCompiler().compile(packet)
    rendered = WorldCardProjectionCompiler().render_text(projection)

    assert packet.active_motion is not None
    assert packet.active_motion["motion_id"] == "motion_demo"
    assert packet.motion_artifact_refs[0]["artifact_kind"] == "preview"
    assert packet.motion_constraints["retarget_profile"] == "ue5_mannequin"
    assert packet.motion_constraints["constraint_types"] == ["root2d", "left-hand"]
    assert packet.motion_constraints["uses_end_effector_constraints"] is True
    assert packet.metadata["motion_freshness"] == "missing_provenance"
    assert any(
        line.startswith("Active motion: motion_demo") for line in projection.summary_lines
    )
    assert "Motion context freshness: missing_provenance" in projection.summary_lines
    assert "Motion artifacts ready: preview" in projection.summary_lines
    assert any(
        line.startswith("motion_timing_policy=") for line in projection.constraints
    )
    assert "motion_freshness=missing_provenance" in projection.constraints
    assert "Active motion: motion_demo" in rendered


def test_world_memory_core_suppresses_stale_motion_but_keeps_provenance_and_artifacts():
    motion_context = {
        "motion_id": "motion_stale",
        "provider": "comfyui_kimodo",
        "status": "completed",
        "updated_at": "2026-04-09T00:00:00Z",
        "expires_at": "2026-04-09T01:00:00Z",
        "source_run_id": "run-motion-stale",
        "artifact_refs": [
            {
                "artifact_kind": "motion_fbx",
                "storage_key": "motion/stale/motion.fbx",
            }
        ],
    }

    snapshot = WorldStateAdapter().normalize_receipt(
        workspace_id="ws_demo",
        profile_id="profile_demo",
        governance_context={"mode": "presentation"},
        motion_context=motion_context,
    )
    packet = WorldStateAdapter().build_packet(snapshot)
    projection = WorldCardProjectionCompiler().compile(packet)

    assert packet.active_motion is None
    assert packet.motion_artifact_refs[0]["artifact_kind"] == "motion_fbx"
    assert packet.metadata["motion_freshness"] == "stale"
    assert packet.metadata["motion_stale_reason"] == "expired"
    assert "Motion context freshness: stale" in projection.summary_lines
    assert "Motion artifacts ready: motion_fbx" in projection.summary_lines
    assert not any(
        line.startswith("Active motion:") for line in projection.summary_lines
    )


def test_world_memory_core_marks_motion_context_fresh_when_provenance_is_present():
    motion_context = {
        "motion_id": "motion_fresh",
        "provider": "comfyui_kimodo",
        "status": "completed",
        "updated_at": "2026-04-10T01:30:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "source_run_id": "exec_motion_fresh",
        "receipt_id": "motion_fresh",
        "freshness_ttl_sec": 21600,
        "artifact_refs": [
            {
                "artifact_kind": "preview",
                "storage_key": "motion/fresh/preview.mp4",
            }
        ],
    }

    snapshot = WorldStateAdapter().normalize_receipt(
        workspace_id="ws_demo",
        profile_id="profile_demo",
        governance_context={"mode": "presentation"},
        motion_context=motion_context,
    )
    packet = WorldStateAdapter().build_packet(snapshot)
    projection = WorldCardProjectionCompiler().compile(packet)

    assert packet.active_motion is not None
    assert packet.active_motion["motion_id"] == "motion_fresh"
    assert packet.metadata["motion_freshness"] == "fresh"
    assert packet.metadata["motion_source_run_id"] == "exec_motion_fresh"
    assert "Motion context freshness: fresh" in projection.summary_lines
