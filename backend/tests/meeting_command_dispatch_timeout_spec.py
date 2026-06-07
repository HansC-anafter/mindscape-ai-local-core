import asyncio
from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.services import meeting_command_dispatch as dispatch_module


def _command() -> MeetingCommandRecord:
    return MeetingCommandRecord(
        command_id="cmd_timeout",
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        thread_id="thread_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Run meeting orchestration",
        status=MeetingCommandStatus.ACCEPTED,
        metadata={},
    )


def _motion_command() -> MeetingCommandRecord:
    return MeetingCommandRecord(
        command_id="cmd_motion",
        workspace_id="ws_demo",
        meeting_id="mtg_motion",
        thread_id="thread_motion",
        origin_surface="workspace_motion_source_practice_launcher",
        actor="user",
        intent_text="AI Yoga Record + summary: create the practice record.",
        status=MeetingCommandStatus.ACCEPTED,
        metadata={},
    )


def test_command_instruction_preserves_canonical_intent_over_raw_summary() -> None:
    envelope = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        intent_text="Create a 90s reels storyboard with 45 scenes.",
        thread_id="thread_demo",
        metadata={"raw_intent_text": "Create storyboard."},
    )

    assert (
        dispatch_module.command_instruction(envelope)
        == "Create a 90s reels storyboard with 45 scenes."
    )


def test_meeting_orchestration_timeout_honors_long_running_metadata() -> None:
    envelope = MeetingCommandEnvelope(
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        intent_text="Create a 90s reels storyboard with 45 scenes.",
        thread_id="thread_demo",
        metadata={"meeting_orchestration_timeout_seconds": 1800},
    )

    assert dispatch_module.meeting_orchestration_timeout_seconds(envelope) == 1800.0


@pytest.mark.asyncio
async def test_dispatch_meeting_orchestration_times_out_with_explicit_result(monkeypatch):
    class _FakeBridge:
        async def build_handoff_in(self, **kwargs):
            return SimpleNamespace(handoff_id="handoff_timeout")

    class _SlowRunner:
        def __init__(self, **kwargs):
            pass

        async def run_meeting_orchestration(self, **kwargs):
            await asyncio.sleep(10)
            return {"status": "completed", "task_ir_id": "should_not_finish"}

    monkeypatch.setattr(
        "backend.app.services.object_runtime.aol_meeting_orchestration_bridge.AOLMeetingOrchestrationBridge",
        _FakeBridge,
    )
    monkeypatch.setattr(
        "backend.app.services.orchestration.meeting.meeting_engine_runner.MeetingEngineRunner",
        _SlowRunner,
    )
    monkeypatch.setattr(
        dispatch_module,
        "meeting_orchestration_timeout_seconds",
        lambda canonical=None: 0.01,
    )

    session = SimpleNamespace(
        id="mtg_demo",
        metadata={
            "request_contract": {
                "addressable_object_layer": {
                    "command_id": "cmd_timeout",
                    "source_ref_count": 2,
                }
            }
        },
    )
    command, dispatch_result = await dispatch_module.dispatch_meeting_orchestration_for_command(
        command=_command(),
        canonical=MeetingCommandEnvelope(
            workspace_id="ws_demo",
            meeting_id="mtg_demo",
            intent_text="Run meeting orchestration",
            thread_id="thread_demo",
            metadata={"dispatch_mode": "route_meeting_orchestration"},
        ),
        session=session,
        workspace=SimpleNamespace(id="ws_demo"),
        store=SimpleNamespace(),
        session_store=SimpleNamespace(),
        workspace_id="ws_demo",
    )

    result = dispatch_result["meeting_orchestration"]
    assert command.status == MeetingCommandStatus.FAILED
    assert command.accepted_task_id is None
    assert command.metadata["dispatch_status"] == "failed"
    assert command.metadata["meeting_orchestration"] == result
    assert result["error_code"] == "meeting_orchestration_timeout"
    assert result["artifact_landing_status"] == "pending"
    assert result["late_result_possible"] is True
    assert result["request_contract_aol_metadata"] == {
        "command_id": "cmd_timeout",
        "source_ref_count": 2,
    }


@pytest.mark.asyncio
async def test_dispatch_playbook_carries_meeting_command_ids_to_runtime_payload():
    captured = {}

    class _FakeOrchestrator:
        async def handle_suggestion_action(self, **kwargs):
            captured.update(kwargs)
            return {
                "task_id": "task_motion_1",
                "triggered_playbook": {"execution_id": "task_motion_1"},
            }

    command, dispatch_result = await dispatch_module.dispatch_playbook_for_command(
        command=_motion_command(),
        canonical=MeetingCommandEnvelope(
            workspace_id="ws_demo",
            meeting_id="mtg_motion",
            origin_surface="workspace_motion_source_practice_launcher",
            intent_text="AI Yoga Record + summary: create the practice record.",
            thread_id="thread_motion",
            requested_action={
                "verb": "execute_playbook",
                "pack_code": "yogacoach",
                "playbook_code": "yogacoach_student_practice_summary",
                "write_mode": "recommendation_only",
                "parameters": {
                    "workspace_id": "ws_demo",
                    "meeting_session_id": "mtg_motion",
                    "capture_session_id": "session_1",
                },
            },
            metadata={
                "dispatch_mode": "route_playbook",
                "explicit_override": True,
                "motion_practice_launch": True,
                "motion_practice_command": True,
            },
        ),
        workspace=SimpleNamespace(
            id="ws_demo",
            owner_user_id="user_demo",
            primary_project_id="project_demo",
        ),
        orchestrator=_FakeOrchestrator(),
        meeting_id="mtg_motion",
    )

    action_params = captured["action_params"]
    request_context = action_params["request_context"]
    assert command.status == MeetingCommandStatus.ACCEPTED
    assert command.accepted_task_id == "task_motion_1"
    assert dispatch_result["playbook"]["triggered_playbook"]["execution_id"] == (
        "task_motion_1"
    )
    assert action_params["command_id"] == "cmd_motion"
    assert action_params["meeting_command_id"] == "cmd_motion"
    assert action_params["motion_practice_command"] is True
    assert request_context["command_id"] == "cmd_motion"
    assert request_context["meeting_command_id"] == "cmd_motion"
    assert request_context["motion_practice_command"] is True
