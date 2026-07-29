from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.dependencies.auth import AuthContext
from backend.app.models.meeting_command import MeetingCommandEnvelope
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.orchestration.meeting.meeting_command_authority import (
    SERVER_AUTHORITY_METADATA_KEY,
    MeetingCommandAuthorityError,
    read_server_authority,
)
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionError,
    MeetingCommandSubmissionService,
)


class _CommandStore:
    def __init__(self) -> None:
        self.saved = []

    def save(self, command):
        self.saved.append(command)
        return command


class _SessionStore:
    def __init__(self, session) -> None:
        self.session = session

    def get_by_id(self, meeting_id):
        return self.session if self.session.id == meeting_id else None


@pytest.mark.asyncio
async def test_submission_replaces_caller_authority_with_authenticated_truth():
    session = MeetingSession.new(workspace_id="ws_allowed")
    session.id = "mtg_allowed"
    store = _CommandStore()
    service = MeetingCommandSubmissionService(
        command_store=store,
        session_store=_SessionStore(session),
    )
    response = await service.submit_envelope(
        envelope=MeetingCommandEnvelope(
            workspace_id="ws_allowed",
            active_group_id="group_allowed",
            meeting_id="mtg_allowed",
            intent_text="Why are birds living dinosaurs?",
            metadata={
                SERVER_AUTHORITY_METADATA_KEY: {
                    "actor_user_id": "attacker",
                    "workspace_id": "ws_other",
                }
            },
        ),
        workspace_id="ws_allowed",
        meeting_id="mtg_allowed",
        workspace=SimpleNamespace(
            id="ws_allowed",
            owner_user_id="workspace_owner",
        ),
        orchestrator=SimpleNamespace(),
        mindscape_store=SimpleNamespace(),
        auth=AuthContext(
            user_id="user_allowed",
            tenant_id="tenant_allowed",
            workspace_ids=["ws_allowed"],
            group_ids=["group_allowed"],
            auth_revision="auth-rev-7",
        ),
    )

    authority = read_server_authority(response.command.metadata)
    assert authority.actor_user_id == "user_allowed"
    assert authority.workspace_id == "ws_allowed"
    assert authority.active_group_id == "group_allowed"
    assert authority.allowed_group_ids == ("group_allowed",)
    assert authority.auth_revision == "auth-rev-7"
    assert authority.source == "authenticated_route"


@pytest.mark.asyncio
async def test_submission_rejects_workspace_outside_authenticated_scope():
    session = MeetingSession.new(workspace_id="ws_forbidden")
    session.id = "mtg_forbidden"
    store = _CommandStore()
    service = MeetingCommandSubmissionService(
        command_store=store,
        session_store=_SessionStore(session),
    )

    with pytest.raises(MeetingCommandSubmissionError) as exc_info:
        await service.submit_envelope(
            envelope=MeetingCommandEnvelope(
                workspace_id="ws_forbidden",
                meeting_id="mtg_forbidden",
                intent_text="Search private knowledge.",
            ),
            workspace_id="ws_forbidden",
            meeting_id="mtg_forbidden",
            workspace=SimpleNamespace(
                id="ws_forbidden",
                owner_user_id="workspace_owner",
            ),
            orchestrator=SimpleNamespace(),
            mindscape_store=SimpleNamespace(),
            auth=AuthContext(
                user_id="user_allowed",
                tenant_id="tenant_allowed",
                workspace_ids=["ws_allowed"],
            ),
        )

    assert exc_info.value.status_code == 403
    assert store.saved == []


def test_read_server_authority_fails_closed_when_missing():
    with pytest.raises(MeetingCommandAuthorityError):
        read_server_authority({})
