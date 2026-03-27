from types import SimpleNamespace

from backend.app.services.orchestration.pack_dispatch_adapter import (
    PackDispatchAdapter,
)


def test_prepare_handoff_uses_request_contract_source_message_for_user_request():
    adapter = PackDispatchAdapter()
    session = SimpleNamespace(
        id="meeting-123",
        thread_id="thread-123",
        metadata={
            "request_contract": {
                "source_message": "[Handoff Intake] 請整理合作方向與立即下一步",
                "acceptance_tests": [],
                "constraints": None,
            }
        },
    )

    inputs = adapter.prepare_handoff(
        playbook_code="project_breakdown",
        raw_inputs={"context": ""},
        session=session,
        project_id="proj-123",
    )

    assert inputs["user_request"] == "[Handoff Intake] 請整理合作方向與立即下一步"
    assert inputs["meeting_session_id"] == "meeting-123"
    assert inputs["project_id"] == "proj-123"


def test_prepare_handoff_does_not_alias_meeting_session_id_to_session_id():
    adapter = PackDispatchAdapter()
    session = SimpleNamespace(
        id="meeting-123",
        thread_id="thread-123",
        metadata={
            "request_contract": {
                "source_message": "[Handoff Intake] 建立來源邊界",
                "acceptance_tests": [],
                "constraints": None,
            }
        },
    )

    inputs = adapter.prepare_handoff(
        playbook_code="pd_reference_compile",
        raw_inputs={},
        session=session,
        project_id="proj-123",
    )

    assert inputs["meeting_session_id"] == "meeting-123"
    assert "session_id" not in inputs
