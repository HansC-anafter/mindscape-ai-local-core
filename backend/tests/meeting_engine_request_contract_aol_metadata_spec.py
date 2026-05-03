from types import SimpleNamespace

from backend.app.services.orchestration.meeting.engine import MeetingEngine


def _bare_engine() -> MeetingEngine:
    engine = object.__new__(MeetingEngine)
    engine.session = SimpleNamespace(workspace_id="ws_demo", metadata={})
    engine.project_id = "project_demo"
    return engine


def test_merge_request_contract_metadata_preserves_aol_handoff_metadata_without_hard_playbook_request():
    engine = _bare_engine()
    aol_metadata = {
        "command_id": "cmd_aol",
        "meeting_id": "mtg_demo",
        "selected_guidance_ids": ["guidance_1"],
        "candidate_playbooks": [
            {
                "source": "selected_guidance",
                "pack_code": "story_direction",
                "playbook_code": "generate_story_asset",
            }
        ],
    }
    handoff_in = SimpleNamespace(
        goals=["Draft storyboard direction"],
        acceptance_tests=[],
        deliverables=[],
        governance_constraints={"addressable_object_layer": aol_metadata},
        context_attachments=[
            {
                "role": "guidance",
                "selected_guidance": ["guidance_1"],
                "selected_guidance_metadata": [
                    {
                        "recommended_pack": "story_direction",
                        "recommended_playbook": "generate_story_asset",
                    }
                ],
            }
        ],
        metadata={"addressable_object_layer": aol_metadata},
        human_instructions="Use selected guidance.",
        requested_output_type=None,
        playbook_requests=None,
        playbook_input_defaults=None,
    )

    metadata = engine._merge_request_contract_metadata(
        contract_data={"playbook_requests": []},
        handoff_in=handoff_in,
        user_message="Use selected guidance.",
    )

    assert metadata["source_message"] == "Use selected guidance."
    assert metadata["workspace_scope"] == "ws_demo"
    assert metadata["addressable_object_layer"] == aol_metadata
    assert metadata["governance_constraints"] == {
        "addressable_object_layer": aol_metadata
    }
    assert metadata["constraints"]["addressable_object_layer"] == aol_metadata
    assert metadata["context_attachments"][0]["selected_guidance"] == ["guidance_1"]
    assert metadata["human_instructions"] == "Use selected guidance."
    assert metadata["goals"] == ["Draft storyboard direction"]
    assert metadata["playbook_requests"] == []


def test_merge_request_contract_metadata_keeps_existing_aol_metadata_when_no_handoff_is_present():
    engine = _bare_engine()
    metadata = engine._merge_request_contract_metadata(
        contract_data={
            "addressable_object_layer": {
                "command_id": "cmd_existing",
                "selected_guidance_ids": [],
            },
            "playbook_requests": [],
        },
        handoff_in=None,
        user_message="Existing contract",
    )

    assert metadata["addressable_object_layer"] == {
        "command_id": "cmd_existing",
        "selected_guidance_ids": [],
    }
    assert metadata["playbook_requests"] == []
