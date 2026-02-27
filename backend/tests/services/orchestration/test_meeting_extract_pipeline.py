"""
Unit tests for MeetingExtractService and the extract pipeline:
events -> typed MeetingExtractItems -> GoalLinking.
"""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass
from typing import Optional, Dict, Any
import uuid

from backend.app.services.orchestration.meeting.extract_service import (
    MeetingExtractService,
)
from backend.app.services.orchestration.meeting.goal_linking_service import (
    GoalLinkingService,
)
from backend.app.models.meeting_extract import (
    MeetingExtract,
    MeetingExtractItem,
    ExtractType,
)
from backend.app.models.goal_set import GoalSet, GoalClause, GoalCategory


@dataclass
class FakeEvent:
    id: str
    event_type: str
    payload: Dict[str, Any]


class TestExtractFromEvents:
    def test_empty_events_produce_empty_extract(self):
        svc = MeetingExtractService()
        extract = svc.extract_from_events(
            meeting_session_id="sess-001",
            events=[],
        )
        assert isinstance(extract, MeetingExtract)
        assert extract.meeting_session_id == "sess-001"
        assert len(extract.items) == 0

    def test_decision_final_classified_as_decision(self):
        evt = FakeEvent(
            id="e1",
            event_type="decision_final",
            payload={"decision": "Approved design", "round_number": 2},
        )
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-001", [evt])
        assert len(extract.items) == 1
        assert extract.items[0].extract_type == ExtractType.DECISION
        assert "Approved design" in extract.items[0].content
        assert extract.items[0].source_event_ids == ["e1"]

    def test_planner_agent_turn_classified_as_action(self):
        evt = FakeEvent(
            id="e2",
            event_type="agent_turn",
            payload={
                "agent_role": "planner",
                "content": "Build landing page",
                "round_number": 1,
            },
        )
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-002", [evt])
        assert len(extract.items) == 1
        assert extract.items[0].extract_type == ExtractType.ACTION

    def test_critic_agent_turn_classified_as_risk(self):
        evt = FakeEvent(
            id="e3",
            event_type="agent_turn",
            payload={
                "agent_role": "critic",
                "content": "Timeline too aggressive",
                "round_number": 1,
            },
        )
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-003", [evt])
        assert len(extract.items) == 1
        assert extract.items[0].extract_type == ExtractType.RISK

    def test_unknown_role_skipped(self):
        evt = FakeEvent(
            id="e4",
            event_type="agent_turn",
            payload={"agent_role": "unknown_role", "content": "Should be ignored"},
        )
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-004", [evt])
        assert len(extract.items) == 0

    def test_empty_content_skipped(self):
        evt = FakeEvent(
            id="e5",
            event_type="decision_final",
            payload={"decision": ""},
        )
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-005", [evt])
        assert len(extract.items) == 0

    def test_mixed_events(self):
        events = [
            FakeEvent("e1", "decision_final", {"decision": "Go ahead"}),
            FakeEvent(
                "e2", "agent_turn", {"agent_role": "planner", "content": "Plan A"}
            ),
            FakeEvent(
                "e3", "agent_turn", {"agent_role": "critic", "content": "Risk B"}
            ),
            FakeEvent("e4", "meeting_start", {"meeting_session_id": "sess-006"}),
        ]
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-006", events)

        types = [i.extract_type for i in extract.items]
        assert ExtractType.DECISION in types
        assert ExtractType.ACTION in types
        assert ExtractType.RISK in types
        assert len(extract.items) == 3  # MEETING_START not classified

    def test_extract_has_unique_ids(self):
        events = [
            FakeEvent("e1", "decision_final", {"decision": "A"}),
            FakeEvent("e2", "decision_final", {"decision": "B"}),
        ]
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-007", events)
        ids = [i.id for i in extract.items]
        assert len(set(ids)) == 2  # unique IDs

    def test_session_id_mismatch_filtered(self):
        evt = FakeEvent(
            id="e1",
            event_type="decision_final",
            payload={"decision": "Wrong session", "meeting_session_id": "other-sess"},
        )
        svc = MeetingExtractService()
        extract = svc.extract_from_events("sess-008", [evt])
        assert len(extract.items) == 0


class TestGoalLinking:
    def _make_clause(self, text, category=GoalCategory.WHAT):
        return GoalClause(
            id=str(uuid.uuid4()),
            category=category,
            text=text,
        )

    def _make_goal_set(self, clauses):
        return GoalSet(
            id="gs-001",
            workspace_id="ws-001",
            clauses=clauses,
        )

    def test_linking_with_keyword_overlap(self):
        clause = self._make_clause("Build a landing page with hero banner")
        goal_set = self._make_goal_set([clause])

        item = MeetingExtractItem(
            id="item-001",
            meeting_session_id="sess-001",
            extract_type=ExtractType.ACTION,
            content="Create a landing page hero banner design",
        )
        extract = MeetingExtract(
            id="ext-001",
            meeting_session_id="sess-001",
            items=[item],
        )

        svc = GoalLinkingService()
        result = svc.link_extract_to_goals(extract, goal_set)
        assert len(result.items[0].goal_clause_ids) > 0
        assert clause.id in result.items[0].goal_clause_ids

    def test_no_linking_when_no_overlap(self):
        clause = self._make_clause("Database schema migration strategy")
        goal_set = self._make_goal_set([clause])

        item = MeetingExtractItem(
            id="item-002",
            meeting_session_id="sess-002",
            extract_type=ExtractType.RISK,
            content="Weather forecasting algorithm accuracy",
        )
        extract = MeetingExtract(
            id="ext-002",
            meeting_session_id="sess-002",
            items=[item],
        )

        svc = GoalLinkingService()
        result = svc.link_extract_to_goals(extract, goal_set)
        assert len(result.items[0].goal_clause_ids) == 0

    def test_linking_with_no_goal_set(self):
        item = MeetingExtractItem(
            id="item-003",
            meeting_session_id="sess-003",
            extract_type=ExtractType.DECISION,
            content="Approved design",
        )
        extract = MeetingExtract(
            id="ext-003",
            meeting_session_id="sess-003",
            items=[item],
        )

        svc = GoalLinkingService()
        result = svc.link_extract_to_goals(extract, None)
        assert len(result.items[0].goal_clause_ids) == 0

    def test_linking_with_empty_clauses(self):
        goal_set = self._make_goal_set([])
        item = MeetingExtractItem(
            id="item-004",
            meeting_session_id="sess-004",
            extract_type=ExtractType.DECISION,
            content="Something",
        )
        extract = MeetingExtract(
            id="ext-004",
            meeting_session_id="sess-004",
            items=[item],
        )

        svc = GoalLinkingService()
        result = svc.link_extract_to_goals(extract, goal_set)
        assert len(result.items[0].goal_clause_ids) == 0
