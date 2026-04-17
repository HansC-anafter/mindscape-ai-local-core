from backend.app.system_capabilities.world_memory_core.services.world_card_projection_compiler import (
    WorldCardProjectionCompiler,
)
from backend.app.system_capabilities.world_memory_core.services.world_state_adapter import (
    WorldStateAdapter,
)


def test_world_memory_core_projects_spatial_schedule_context_into_packet_and_world_card():
    spatial_schedule_context = {
        "schedule_id": "ssched_demo",
        "status": "planned",
        "title": "Blocking pass",
        "entity_kinds": ["actor", "camera"],
        "active_segment_ids": ["segment_1", "segment_2"],
        "segment_count": 2,
        "time_window": {"start_index": 0, "end_index": 1},
        "constraint_summary": {"motion_constraint_count": 2},
        "artifact_refs": [
            {
                "artifact_id": "task-demo/artifacts/spatial_schedule",
                "artifact_type": "application/vnd.mindscape.spatial-scheduling+json",
                "uri": "task-ir://task-demo/artifacts/spatial_schedule",
            }
        ],
        "consumer_refs": [
            {
                "consumer_code": "motion_runtime",
                "status": "ready",
                "receipt_artifact_id": "motion/task-demo",
            }
        ],
        "revision_refs": [
            {
                "schedule_id": "ssched_prev",
                "artifact_id": "task-demo/artifacts/spatial_schedule_prev",
                "artifact_type": "application/vnd.mindscape.spatial-scheduling+json",
                "updated_at": "2026-04-15T12:00:00+00:00",
                "relationship": "supersedes",
            }
        ],
        "updated_at": "2026-04-16T12:00:00+00:00",
    }

    snapshot = WorldStateAdapter().normalize_receipt(
        workspace_id="ws_demo",
        profile_id="profile_demo",
        governance_context={"mode": "presentation"},
        spatial_schedule_context=spatial_schedule_context,
    )
    packet = WorldStateAdapter().build_packet(snapshot)
    projection = WorldCardProjectionCompiler().compile(packet)
    rendered = WorldCardProjectionCompiler().render_text(projection)

    assert packet.active_schedule is not None
    assert packet.active_schedule["schedule_id"] == "ssched_demo"
    assert packet.active_schedule["consumer_refs"] == [
        {
            "consumer_code": "motion_runtime",
            "status": "ready",
            "receipt_artifact_id": "motion/task-demo",
        }
    ]
    assert packet.active_schedule["revision_refs"] == [
        {
            "schedule_id": "ssched_prev",
            "artifact_ref": {
                "artifact_id": "task-demo/artifacts/spatial_schedule_prev",
                "type": "application/vnd.mindscape.spatial-scheduling+json",
            },
            "updated_at": "2026-04-15T12:00:00+00:00",
            "relation": "supersedes",
        }
    ]
    assert packet.schedule_artifact_refs[0]["artifact_id"] == "task-demo/artifacts/spatial_schedule"
    assert packet.schedule_constraints["motion_constraint_count"] == 2
    assert any(
        line.startswith("Active schedule: Blocking pass") for line in projection.summary_lines
    )
    assert any(
        line.startswith("schedule_motion_constraint_count=")
        for line in projection.constraints
    )
    assert "Active schedule: Blocking pass" in rendered
