"""Tests for MeetingSupervisor (L5 supervision layer)."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from backend.app.services.orchestration.meeting.meeting_supervisor import (
    MeetingSupervisor,
)


def _make_task(task_id, status, updated_minutes_ago=5, title=""):
    """Helper to create a mock task."""
    t = MagicMock()
    t.id = task_id
    t.title = title
    t.status = status
    t.updated_at = datetime.now(timezone.utc) - timedelta(minutes=updated_minutes_ago)
    return t


class TestCheckStuckTasks:

    @pytest.mark.asyncio
    async def test_finds_stuck_pending_task(self):
        old_pending = _make_task("t1", "pending", updated_minutes_ago=60)
        recent_running = _make_task("t2", "running", updated_minutes_ago=5)
        completed = _make_task("t3", "completed", updated_minutes_ago=120)

        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = [
            old_pending,
            recent_running,
            completed,
        ]
        sup = MeetingSupervisor(tasks_store=store)
        stuck = await sup.check_stuck_tasks("sess-1", stuck_threshold_minutes=30)

        assert len(stuck) == 1
        assert stuck[0]["task_id"] == "t1"
        assert stuck[0]["minutes_stuck"] >= 59

    @pytest.mark.asyncio
    async def test_no_stuck_when_all_completed(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = [
            _make_task("t1", "completed"),
            _make_task("t2", "failed"),
        ]
        sup = MeetingSupervisor(tasks_store=store)
        stuck = await sup.check_stuck_tasks("sess-1")
        assert stuck == []


class TestScoreSession:

    @pytest.mark.asyncio
    async def test_score_partial(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = [
            _make_task("t1", "completed"),
            _make_task("t2", "completed"),
            _make_task("t3", "failed"),
        ]
        sup = MeetingSupervisor(tasks_store=store)
        score = await sup.score_session("sess-1")
        assert abs(score - 2 / 3) < 0.01

    @pytest.mark.asyncio
    async def test_score_empty_session(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = []
        sup = MeetingSupervisor(tasks_store=store)
        score = await sup.score_session("sess-1")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_score_all_failed(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = [
            _make_task("t1", "failed"),
            _make_task("t2", "failed"),
        ]
        sup = MeetingSupervisor(tasks_store=store)
        score = await sup.score_session("sess-1")
        assert score == 0.0


class TestOnSessionClosed:

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = [
            _make_task("t1", "completed", updated_minutes_ago=5),
            _make_task("t2", "pending", updated_minutes_ago=60, title="Stuck task"),
            _make_task("t3", "failed", updated_minutes_ago=10),
        ]
        sup = MeetingSupervisor(tasks_store=store)
        result = await sup.on_session_closed("sess-1")

        assert result["session_id"] == "sess-1"
        assert result["total_tasks"] == 3
        assert result["completed"] == 1
        assert result["failed"] == 1
        assert result["stuck"] == 1
        assert abs(result["score"] - 1 / 3) < 0.01

    @pytest.mark.asyncio
    async def test_empty_session(self):
        store = MagicMock()
        store.list_tasks_by_meeting_session.return_value = []
        sup = MeetingSupervisor(tasks_store=store)
        result = await sup.on_session_closed("sess-empty")

        assert result["total_tasks"] == 0
        assert result["score"] == 1.0
