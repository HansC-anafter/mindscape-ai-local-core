from backend.app.services.orchestration.meeting.engine import MeetingEngine


def _quality_requirements(scene_count=45):
    return {
        "target": {
            "deliverable_kind": "90s_reels_storyboard",
            "scene_count_target": scene_count,
            "scene_count_floor": 40,
            "total_duration_sec": 90,
        },
        "content_quality": {
            "require_per_scene_judge": True,
            "require_reference_grounding": True,
            "require_concrete_scene_copy": True,
        },
        "rewrite_until_quality_passed": True,
        "producer_review_required": True,
    }


def test_request_contract_metadata_uses_quality_scene_count_for_scale():
    metadata = {
        "deliverables": [
            {
                "id": "D1",
                "name": "90s Reels storyboard",
                "quantity": 1,
                "requires": [],
            }
        ],
        "constraints": {"quality_requirements": _quality_requirements()},
        "scale_estimate": "trivial",
    }

    MeetingEngine._apply_quality_target_to_request_contract_metadata(metadata)

    assert metadata["deliverables"][0]["quantity"] == 45
    assert metadata["scale_estimate"] == "program"


def test_quality_storyboard_contract_requires_full_deliberation_review():
    engine = object.__new__(MeetingEngine)
    engine._get_request_contract_metadata = lambda: {
        "constraints": {"quality_requirements": _quality_requirements()}
    }

    assert engine._requires_full_deliberation_review() is True
