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
    assert any(
        line.startswith("Active motion: motion_demo") for line in projection.summary_lines
    )
    assert any(
        line.startswith("motion_timing_policy=") for line in projection.constraints
    )
    assert "Active motion: motion_demo" in rendered
