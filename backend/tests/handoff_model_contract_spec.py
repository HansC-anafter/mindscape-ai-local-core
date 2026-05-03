from backend.app.models.handoff import HandoffIn


def test_handoff_in_does_not_derive_pack_specific_playbook_requests():
    handoff = HandoffIn(
        handoff_id="handoff_pd_seed",
        workspace_id="ws_demo",
        intent_summary="Use pack-owned seed data",
        governance_constraints={
            "pd_storyboard_seed": {
                "workspace_id": "ws_demo",
                "session_id": "ds_demo",
            }
        },
    )

    assert handoff.playbook_requests is None


def test_handoff_in_preserves_explicit_generic_playbook_requests():
    handoff = HandoffIn(
        handoff_id="handoff_explicit",
        workspace_id="ws_demo",
        intent_summary="Run explicit downstream workflow",
        playbook_requests=[
            {
                "playbook_code": "example_playbook",
                "input_params": {"workspace_id": "ws_demo"},
            }
        ],
    )

    assert handoff.playbook_requests == [
        {
            "playbook_code": "example_playbook",
            "input_params": {"workspace_id": "ws_demo"},
        }
    ]
