from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandStatus,
    MeetingRequestedAction,
)
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionError,
    MeetingCommandSubmissionService,
)


class _FakeCommandStore:
    def __init__(self) -> None:
        self.saved = []

    def save(self, command):
        self.saved.append(command)
        return command

    def list_by_meeting(self, **kwargs):
        return list(self.saved)


class _FakeSessionStore:
    def __init__(self, session):
        self.session = session

    def get_by_id(self, meeting_id):
        if self.session and self.session.id == meeting_id:
            return self.session
        return None


class _FakeMindscapeStore:
    def __init__(self) -> None:
        self.events = []

    def create_event(self, event, generate_embedding=False):
        assert generate_embedding is False
        self.events.append(event)
        return event


@pytest.mark.asyncio
async def test_submission_service_preserves_existing_command_response_shape() -> None:
    session = MeetingSession.new(workspace_id="ws_voice", thread_id="thread_voice")
    session.id = "mtg_voice"
    command_store = _FakeCommandStore()
    service = MeetingCommandSubmissionService(
        command_store=command_store,
        session_store=_FakeSessionStore(session),
    )

    response = await service.submit_envelope(
        envelope=MeetingCommandEnvelope(
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            intent_text="Start the coaching summary.",
            origin_surface="meeting_voice",
            metadata={"client_turn_id": "turn_1"},
        ),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(
            id="ws_voice",
            owner_user_id="profile_voice",
        ),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
    )

    assert response.workspace_id == "ws_voice"
    assert response.meeting_id == "mtg_voice"
    assert response.status == MeetingCommandStatus.ACCEPTED
    assert response.command.thread_id == "thread_voice"
    assert response.command.origin_surface == "meeting_voice"
    assert response.command.metadata["client_turn_id"] == "turn_1"
    assert response.command.metadata["dispatch_status"] == "pending_runtime_integration"
    assert len(command_store.saved) == 1


@pytest.mark.asyncio
async def test_submission_service_rejects_workspace_mismatch_without_save() -> None:
    session = MeetingSession.new(workspace_id="ws_voice")
    session.id = "mtg_voice"
    command_store = _FakeCommandStore()
    service = MeetingCommandSubmissionService(
        command_store=command_store,
        session_store=_FakeSessionStore(session),
    )

    with pytest.raises(MeetingCommandSubmissionError) as exc_info:
        await service.submit_envelope(
            envelope=MeetingCommandEnvelope(
                workspace_id="wrong",
                meeting_id="mtg_voice",
                intent_text="Start.",
            ),
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            workspace=SimpleNamespace(id="ws_voice"),
            orchestrator=SimpleNamespace(),
            mindscape_store=SimpleNamespace(),
        )

    assert exc_info.value.status_code == 400
    assert command_store.saved == []


@pytest.mark.asyncio
async def test_client_action_commits_capability_event_after_completed_ledger_row() -> None:
    session = MeetingSession.new(workspace_id="ws_voice", thread_id="thread_voice")
    session.id = "mtg_voice"
    command_store = _FakeCommandStore()
    event_store = _FakeMindscapeStore()
    service = MeetingCommandSubmissionService(
        command_store=command_store,
        session_store=_FakeSessionStore(session),
    )

    response = await service.submit_envelope(
        envelope=MeetingCommandEnvelope(
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            intent_text="播放瑜伽練習",
            origin_surface="meeting_voice",
            requested_action=MeetingRequestedAction(
                verb="client_action",
                pack_code="yogacoach",
                affordance_verb="yogacoach.prepare_reference_practice",
                parameters={
                    "client_action": {
                        "schema_version": "aol.client_action.v1",
                        "pack_code": "yogacoach",
                        "intent_code": "prepare_default_reference_practice",
                        "action_code": "yogacoach.prepare_reference_practice",
                        "requires_confirmation": True,
                        "payload": {"playback": {"duration_ms": 1_800_000}},
                    }
                },
            ),
            metadata={
                "dispatch_mode": "route_client_action",
                "explicit_override": True,
            },
        ),
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        workspace=SimpleNamespace(id="ws_voice", owner_user_id="profile_voice"),
        orchestrator=SimpleNamespace(),
        mindscape_store=event_store,
    )

    assert response.status == MeetingCommandStatus.COMPLETED
    assert command_store.saved[-1].status == MeetingCommandStatus.COMPLETED
    assert len(event_store.events) == 1
    event = event_store.events[0]
    assert event.event_type.value == "capability_event"
    assert event.payload["event_code"] == "aol_client_action_ready"
    assert event.payload["command_id"] == response.command_id
    assert event.payload["client_action"]["pack_code"] == "yogacoach"
