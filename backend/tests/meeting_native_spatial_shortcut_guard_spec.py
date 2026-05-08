from types import SimpleNamespace

from backend.app.services.orchestration.meeting.engine import MeetingEngine


def _engine_with_contract(contract):
    engine = object.__new__(MeetingEngine)
    engine.executor_runtime = "codex_cli"
    engine.session = SimpleNamespace(
        agenda=["45 scenes storyboard with camera and performance requirements"],
        title="",
        metadata={"request_contract": contract},
    )
    return engine


def test_aol_candidate_contract_bypasses_native_spatial_shortcut() -> None:
    engine = _engine_with_contract(
        {
            "constraints": {
                "addressable_object_layer": {
                    "candidate_playbooks": [
                        {
                            "pack_code": "performance_direction",
                            "playbook_code": "pd_storyboard_gen",
                        }
                    ]
                },
                "quality_requirements": {
                    "target": {
                        "scene_count": 45,
                        "visual_scope": "storyboard_frames",
                    }
                },
            }
        }
    )

    assert engine._should_use_single_turn_native_spatial_planner("45 scenes storyboard") is False
    assert (
        engine._use_native_spatial_planner_mode("planner", "45 scenes storyboard")
        is False
    )


def test_native_spatial_shortcut_remains_available_without_affordance_contract() -> None:
    engine = _engine_with_contract({})

    assert (
        engine._should_use_single_turn_native_spatial_planner(
            "single scene camera blocking"
        )
        is False
    )
    assert (
        engine._should_use_single_turn_native_spatial_planner(
            "Design a bounded spatial handoff scene for Blender downstream playback"
        )
        is True
    )
