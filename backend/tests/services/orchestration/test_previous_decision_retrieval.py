"""
Unit tests for _build_previous_decisions_context:
DECISION_FINAL event query with minutes_md fallback.
"""

import pytest
from unittest.mock import MagicMock


from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin
from backend.app.models.mindscape import EventType


class FakePreviousSession:
    def __init__(self, session_id="prev-sess", is_active=False):
        self.id = session_id
        self.is_active = is_active
        self.minutes_md = None
        self.action_items = []


class StubEngine(MeetingPromptsMixin):
    def __init__(self):
        self.session = MagicMock()
        self.session.id = "current-sess"
        self.session.workspace_id = "ws-001"
        self.workspace = MagicMock()
        self.workspace.id = "ws-001"
        self.project_id = "proj-001"
        self.store = MagicMock()
        self.session_store = MagicMock()
        self._effective_lens = None
        self._active_intent_ids = []
        self._events = []


class TestPreviousDecisionsFromEvents:
    def test_returns_empty_when_no_project(self):
        engine = StubEngine()
        engine.project_id = None
        assert engine._build_previous_decisions_context() == ""

    def test_returns_empty_when_no_session_store(self):
        engine = StubEngine()
        engine.session_store = None
        assert engine._build_previous_decisions_context() == ""

    def test_returns_empty_when_no_previous_session(self):
        engine = StubEngine()
        engine.session_store.list_by_workspace.return_value = []
        assert engine._build_previous_decisions_context() == ""

    def test_skips_current_session(self):
        engine = StubEngine()
        current = FakePreviousSession(session_id="current-sess", is_active=True)
        engine.session_store.list_by_workspace.return_value = [current]
        assert engine._build_previous_decisions_context() == ""

    def test_queries_decision_final_events(self):
        """When DECISION_FINAL events exist, they are used over minutes_md."""
        engine = StubEngine()
        prev = FakePreviousSession()
        prev.minutes_md = "Should be ignored"
        engine.session_store.list_by_workspace.return_value = [prev]

        # Mock store.get_events_by_meeting_session to return DECISION_FINAL events
        fake_event = MagicMock()
        fake_event.event_type = EventType.DECISION_FINAL
        fake_event.payload = {
            "decision": "Approved the design",
            "round_number": 2,
        }
        engine.store.get_events_by_meeting_session.return_value = [fake_event]

        result = engine._build_previous_decisions_context()
        assert "Previous meeting decisions:" in result
        assert "Approved the design" in result
        assert "[R2]" in result
        # minutes_md should NOT appear when events are found
        assert "Should be ignored" not in result

    def test_falls_back_to_minutes_when_no_events(self):
        """When no DECISION_FINAL events, fall back to minutes_md."""
        engine = StubEngine()
        prev = FakePreviousSession()
        prev.minutes_md = "Meeting concluded with alignment on roadmap."
        engine.session_store.list_by_workspace.return_value = [prev]

        # No DECISION_FINAL events
        engine.store.get_events_by_meeting_session.return_value = []

        result = engine._build_previous_decisions_context()
        assert "Previous meeting summary:" in result
        assert "roadmap" in result

    def test_falls_back_when_list_events_raises(self):
        """When store.list_events raises, fall back to minutes_md."""
        engine = StubEngine()
        prev = FakePreviousSession()
        prev.minutes_md = "Fallback content here."
        engine.session_store.list_by_workspace.return_value = [prev]
        engine.store.get_events_by_meeting_session.side_effect = AttributeError(
            "no such method"
        )

        result = engine._build_previous_decisions_context()
        assert "Fallback content here" in result

    def test_includes_action_items(self):
        engine = StubEngine()
        prev = FakePreviousSession()
        prev.action_items = [
            {"title": "Deploy to staging", "status": "done"},
            {"title": "Review PR", "status": "pending"},
        ]
        engine.session_store.list_by_workspace.return_value = [prev]
        engine.store.get_events_by_meeting_session.return_value = []

        result = engine._build_previous_decisions_context()
        assert "Deploy to staging" in result
        assert "[done]" in result
        assert "Review PR" in result

    def test_truncates_long_minutes(self):
        engine = StubEngine()
        prev = FakePreviousSession()
        prev.minutes_md = "x" * 1000
        engine.session_store.list_by_workspace.return_value = [prev]
        engine.store.get_events_by_meeting_session.return_value = []

        result = engine._build_previous_decisions_context()
        assert "(truncated)" in result
