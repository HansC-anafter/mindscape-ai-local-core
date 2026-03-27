from __future__ import annotations

import pytest
from types import SimpleNamespace

from backend.app.models.meeting_session import MeetingSession
from backend.app.services.orchestration.meeting.engine import MeetingEngine


class _FakeSessionStore:
    def __init__(self) -> None:
        self.updated_sessions: list[MeetingSession] = []

    def update(self, session: MeetingSession) -> None:
        self.updated_sessions.append(session)


class _PipelineHarness(MeetingEngine):
    def __init__(self, session: MeetingSession) -> None:
        self.session = session
        self.session_store = _FakeSessionStore()
        self.workspace = SimpleNamespace(id=session.workspace_id)
        self.profile_id = "profile-001"
        self.thread_id = session.thread_id
        self.project_id = session.project_id

    async def _stage_agenda_and_rag(self, user_message: str) -> None:
        raise RuntimeError("agenda stage stalled")

    async def _stage_compile_contract(self, user_message: str) -> None:
        raise AssertionError("compile_contract should not run after agenda failure")

    async def _stage_deliberation(self, user_message: str):
        raise AssertionError("deliberation should not run after agenda failure")


@pytest.mark.asyncio
async def test_run_persists_pipeline_stage_on_pre_deliberation_failure():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace stalled compile"],
    )
    engine = _PipelineHarness(session=session)

    with pytest.raises(RuntimeError, match="agenda stage stalled"):
        await engine.run("Investigate stalled compile")

    assert session.status.value == "failed"
    assert session.round_count == 0
    assert session.metadata["pipeline_stage"] == "agenda_and_rag"
    assert session.metadata["pipeline_stage_status"] == "failed"
    assert session.metadata["pipeline_stage_error"] == "agenda stage stalled"
    assert session.metadata["pipeline_failure"]["before_deliberation"] is True
    assert session.metadata["pipeline_failure"]["stage"] == "agenda_and_rag"
    assert session.ended_at is not None
    assert engine.session_store.updated_sessions
    assert session.metadata["pipeline_stage_history"][0]["status"] == "started"
    assert session.metadata["pipeline_stage_history"][-1]["status"] == "failed"
