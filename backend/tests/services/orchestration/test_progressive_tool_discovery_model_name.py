from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_model_name_forwarded_on_new_session():
    with (
        patch(
            "backend.app.services.conversation.pipeline_meeting_core.session_lifecycle.decompose_agenda",
            new_callable=AsyncMock,
            return_value=["task A", "task B"],
        ) as mock_decompose,
        patch(
            "backend.app.services.conversation.pipeline_meeting_core.session_lifecycle._resolve_lens_id",
            return_value=None,
        ),
        patch(
            "backend.app.models.meeting_session.MeetingSession",
        ) as mock_session_cls,
    ):
        mock_session_cls.new.return_value = MagicMock(id="s1")
        mock_store = MagicMock()
        mock_store.get_active_session.return_value = None
        mock_store.create = MagicMock()

        from backend.app.services.conversation.pipeline_meeting import (
            ensure_meeting_session,
        )

        await ensure_meeting_session(
            "ws1",
            "t1",
            mock_store,
            project_id=None,
            user_message="Research and write posts",
            model_name="gemini-2.5-pro",
        )
        _, kwargs = mock_decompose.call_args
        assert kwargs["model_name"] == "gemini-2.5-pro"
        assert kwargs["executor_runtime"] is None


@pytest.mark.asyncio
async def test_model_name_forwarded_on_reuse():
    existing = MagicMock()
    existing.id = "s-existing"
    existing.agenda = ["old item"]

    with patch(
        "backend.app.services.conversation.pipeline_meeting_core.agenda.decompose_agenda",
        new_callable=AsyncMock,
        return_value=["new A", "new B"],
    ) as mock_decompose:
        mock_store = MagicMock()
        mock_store.get_active_session.return_value = existing
        mock_store.update = MagicMock()

        from backend.app.services.conversation.pipeline_meeting import (
            ensure_meeting_session,
        )

        await ensure_meeting_session(
            "ws1",
            "t1",
            mock_store,
            project_id=None,
            user_message="New multi-step request",
            model_name="claude-3-5-sonnet",
        )
        _, kwargs = mock_decompose.call_args
        assert kwargs["model_name"] == "claude-3-5-sonnet"
        assert kwargs["executor_runtime"] is None
