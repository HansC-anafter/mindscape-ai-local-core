"""
Unit tests for A3 decision provenance: lens_hash and intent_ids
enrichment on AGENT_TURN and DECISION_FINAL events.
"""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from backend.app.services.orchestration.meeting._events import MeetingEventsMixin


class FakeSession:
    def __init__(self):
        self.id = "sess-prov-001"
        self.workspace_id = "ws-001"
        self.lens_id = "lens-001"


class StubEngine(MeetingEventsMixin):
    """Minimal stub for testing event emission."""

    def __init__(self):
        self.session = FakeSession()
        self.profile_id = "user-001"
        self.project_id = "proj-001"
        self.thread_id = "thread-001"
        self._events = []
        self._effective_lens = None
        self._lens_hash = None
        self._active_intent_ids = []

    def _emit_event(self, event_type, payload):
        """Capture emitted events for inspection."""
        self._events.append({"event_type": event_type, "payload": payload})

    def _get_active_intent_ids(self):
        """Return cached active intent IDs (from _governance.py mixin)."""
        return self._active_intent_ids


@dataclass
class FakeTurnResult:
    agent_id: str
    agent_role: str
    round_number: int
    content: str
    converged: bool = False


class TestEmitTurnProvenance:
    def test_turn_event_includes_lens_hash(self):
        engine = StubEngine()
        engine._lens_hash = "abc123"
        turn = FakeTurnResult("a1", "planner", 1, "Let us plan")
        engine._emit_turn(turn)
        assert len(engine._events) == 1
        payload = engine._events[0]["payload"]
        assert payload["lens_hash"] == "abc123"

    def test_turn_event_lens_hash_none_when_no_lens(self):
        engine = StubEngine()
        turn = FakeTurnResult("a1", "critic", 1, "I disagree")
        engine._emit_turn(turn)
        payload = engine._events[0]["payload"]
        assert payload.get("lens_hash") is None

    def test_turn_event_includes_intent_ids(self):
        engine = StubEngine()
        engine._active_intent_ids = ["i1", "i2"]
        turn = FakeTurnResult("a1", "planner", 1, "Plan")
        engine._emit_turn(turn)
        payload = engine._events[0]["payload"]
        assert payload["intent_ids"] == ["i1", "i2"]


class TestDecisionFinalProvenance:
    def test_decision_final_full_provenance(self):
        engine = StubEngine()
        engine._lens_hash = "hash-xyz"
        engine._active_intent_ids = ["i1", "i2"]
        engine._emit_decision_final(decision="Approved design", round_number=3)
        assert len(engine._events) == 1
        payload = engine._events[0]["payload"]

        assert payload["decision"] == "Approved design"
        assert payload["round_number"] == 3
        assert payload["lens_id"] == "lens-001"
        assert payload["lens_hash"] == "hash-xyz"
        assert payload["intent_ids"] == ["i1", "i2"]
        assert "input_context_summary" in payload

    def test_decision_final_without_lens(self):
        engine = StubEngine()
        engine._emit_decision_final(decision="Proceed", round_number=1)
        payload = engine._events[0]["payload"]
        assert payload["lens_id"] == "lens-001"
        assert payload.get("lens_hash") is None
        assert payload["intent_ids"] == []

    def test_decision_includes_meeting_session_id(self):
        engine = StubEngine()
        engine._emit_decision_final(decision="Go", round_number=2)
        payload = engine._events[0]["payload"]
        assert payload["meeting_session_id"] == "sess-prov-001"
