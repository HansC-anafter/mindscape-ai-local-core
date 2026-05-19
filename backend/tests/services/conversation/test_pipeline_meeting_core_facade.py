from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services.conversation import pipeline_meeting
from backend.app.services.conversation.pipeline_meeting_core import (
    adapters,
    agenda,
    finalization,
    project_flags,
    session_lifecycle,
)


def test_pipeline_meeting_facade_surface_and_aliases():
    expected = [
        "_sanitize_agenda_item",
        "_append_agenda_if_needed",
        "_decompose_agenda",
        "build_execution_launcher",
        "extract_handoff_in",
        "persist_meeting_task_ir",
        "ensure_meeting_session",
        "is_project_meeting_enabled",
        "finalize_meeting_session",
    ]

    assert [name for name in expected if not hasattr(pipeline_meeting, name)] == []
    assert pipeline_meeting._sanitize_agenda_item is agenda.sanitize_agenda_item
    assert pipeline_meeting._append_agenda_if_needed is agenda.append_agenda_if_needed
    assert pipeline_meeting._decompose_agenda is agenda.decompose_agenda
    assert pipeline_meeting.build_execution_launcher is adapters.build_execution_launcher
    assert pipeline_meeting.extract_handoff_in is adapters.extract_handoff_in
    assert pipeline_meeting.persist_meeting_task_ir is adapters.persist_meeting_task_ir
    assert pipeline_meeting.ensure_meeting_session is session_lifecycle.ensure_meeting_session
    assert pipeline_meeting.is_project_meeting_enabled is project_flags.is_project_meeting_enabled
    assert pipeline_meeting.finalize_meeting_session is finalization.finalize_meeting_session


@pytest.mark.asyncio
async def test_agenda_decompose_reads_json_fenced_response():
    async def fake_generate(messages, model):
        assert model == "model-a"
        assert messages[0]["role"] == "system"
        return '```json\n["research topic","draft outline"]\n```'

    items = await agenda.decompose_agenda(
        "Please research the topic and draft an outline",
        model_name="model-a",
        llm_generate_fn=fake_generate,
    )

    assert items == ["research topic", "draft outline"]


@pytest.mark.asyncio
async def test_agenda_decompose_falls_back_without_model():
    item = "Summarize this request for a meeting agenda"

    items = await agenda.decompose_agenda(
        item,
        model_name=None,
        llm_generate_fn=MagicMock(),
    )

    assert items == [item]


@pytest.mark.asyncio
async def test_ensure_meeting_session_reuses_explicit_session():
    session = SimpleNamespace(
        id="meeting-1",
        workspace_id="ws-1",
        project_id=None,
        thread_id=None,
        is_active=True,
        agenda=[],
    )
    store = MagicMock()
    store.get_by_id.return_value = session

    result = await session_lifecycle.ensure_meeting_session(
        "ws-1",
        "thread-1",
        store,
        project_id="project-1",
        user_message="Discuss research plan",
        explicit_session_id="meeting-1",
    )

    assert result is session
    assert session.project_id == "project-1"
    assert session.thread_id == "thread-1"
    assert session.agenda == ["Discuss research plan"]
    store.get_active_session.assert_not_called()
    store.create.assert_not_called()
    assert store.update.call_count >= 1


@pytest.mark.asyncio
async def test_ensure_meeting_session_returns_none_for_workspace_mismatch():
    session = SimpleNamespace(
        id="meeting-1",
        workspace_id="ws-other",
        project_id=None,
        thread_id=None,
        is_active=True,
        agenda=[],
    )
    store = MagicMock()
    store.get_by_id.return_value = session

    result = await session_lifecycle.ensure_meeting_session(
        "ws-1",
        "thread-1",
        store,
        explicit_session_id="meeting-1",
    )

    assert result is None
    store.get_active_session.assert_not_called()
    store.create.assert_not_called()


@pytest.mark.asyncio
async def test_project_meeting_enabled_strict_boolean():
    store = SimpleNamespace(
        get_project=MagicMock(
            side_effect=[
                SimpleNamespace(metadata={"meeting_enabled": True}),
                SimpleNamespace(metadata={"meeting_enabled": "true"}),
                SimpleNamespace(metadata={"meeting_enabled": "1"}),
            ]
        )
    )

    assert await project_flags.is_project_meeting_enabled("p1", store) is True
    assert await project_flags.is_project_meeting_enabled("p2", store) is True
    assert await project_flags.is_project_meeting_enabled("p3", store) is False


@pytest.mark.asyncio
async def test_finalize_meeting_session_updates_metadata_without_decision_pollution():
    session = SimpleNamespace(
        id="meeting-1",
        metadata={},
        decisions=["decision-event-1"],
    )
    store = MagicMock()
    store.get_by_id.return_value = session
    result = SimpleNamespace(
        meeting_session_id="meeting-1",
        playbook_code="pack.alpha",
        execution_id="exec-1",
        success=True,
        error=None,
        completion_status="accepted",
    )

    await finalization.finalize_meeting_session(result, store)

    assert session.decisions == ["decision-event-1"]
    assert session.metadata["runs"] == [
        {
            "playbook": "pack.alpha",
            "execution_id": "exec-1",
            "success": True,
            "error": None,
        }
    ]
    assert session.metadata["completion_status"] == "accepted"
    store.update.assert_called_once_with(session)
