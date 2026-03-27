from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
    check_dispatch_policy,
)


def test_policy_gate_uses_request_contract_source_message_for_user_request():
    action_items = [
        {
            "title": "整理合作方向三點與立即下一步",
            "intent_id": "intent-1",
            "playbook_code": "project_breakdown",
            "input_params": {
                "deliverables": ["D1", "D2"],
            },
        }
    ]

    report = check_dispatch_policy(
        action_items=action_items,
        workspace_id="ws-test",
        available_playbooks_cache="- project_breakdown: Project Breakdown",
        session_metadata={
            "request_contract": {
                "source_message": "[Handoff Intake] 請整理合作方向與立即下一步",
                "acceptance_tests": [],
                "constraints": None,
            }
        },
    )

    assert report["blocked_count"] == 0
    assert report["items"][0]["status"] == "allowed"
    assert action_items[0]["policy_gate"]["status"] == "allowed"


def test_policy_gate_does_not_alias_meeting_session_id_to_session_id():
    action_items = [
        {
            "title": "建立來源邊界與事實矩陣",
            "intent_id": "intent-2",
            "playbook_code": "pd_reference_compile",
            "input_params": {
                "objective": "建立唯一內容依據",
            },
        }
    ]

    report = check_dispatch_policy(
        action_items=action_items,
        workspace_id="ws-test",
        available_playbooks_cache="- pd_reference_compile: Reference Compile",
        meeting_session_id="meeting-123",
        session_metadata={
            "request_contract": {
                "source_message": "[Handoff Intake] 建立來源邊界",
                "acceptance_tests": [],
                "constraints": None,
            }
        },
    )

    assert report["blocked_count"] == 1
    assert report["items"][0]["blocks"][0]["missing_fields"] == ["session_id"]
    assert action_items[0]["landing_status"] == "policy_blocked"
