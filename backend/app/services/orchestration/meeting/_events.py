"""
Meeting engine event emission mixin.

Handles emitting structured MindEvents for each stage of the meeting lifecycle
(round start/end, agent turns, decisions, action items, state vector).
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.models.mindscape import EventActor, EventType, MindEvent


class MeetingEventsMixin:
    """Mixin providing event emission methods for MeetingEngine."""

    def _emit_turn(self, turn: Any) -> None:
        """Emit an AGENT_TURN event enriched with governance trace metadata."""
        self._emit_event(
            EventType.AGENT_TURN,
            payload={
                "meeting_session_id": self.session.id,
                "agent_id": turn.agent_id,
                "agent_role": turn.agent_role,
                "round_number": turn.round_number,
                "content": turn.content,
                "lens_id": self.session.lens_id,
                "lens_hash": getattr(self, "_lens_hash", None),
                "intent_ids": self._get_active_intent_ids(),
                "evidence_refs": self._extract_evidence_from_content(turn.content),
            },
        )

    def _extract_evidence_from_content(self, content: str) -> List[str]:
        """Extract evidence markers from turn content (URLs, file refs, explicit markers)."""
        refs: List[str] = []
        for _, url in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content):
            refs.append(url)
        for m in re.findall(
            r"(?:evidence|source|reference|ref):\s*(.+?)(?:\n|$)",
            content,
            re.IGNORECASE,
        ):
            refs.append(m.strip())
        return refs[:10]

    def _emit_decision_proposal(self, turn: Any) -> None:
        """Emit a DECISION_PROPOSAL event from a planner turn."""
        self._emit_event(
            EventType.DECISION_PROPOSAL,
            payload={
                "meeting_session_id": self.session.id,
                "proposed_by": turn.agent_id,
                "round_number": turn.round_number,
                "proposal": turn.content,
                "supporting_evidence": [],
                "risks": [],
                "alternatives": [],
            },
        )

    def _emit_decision_final(self, decision: str, round_number: int) -> None:
        """Emit a DECISION_FINAL event with full provenance chain."""
        self._emit_event(
            EventType.DECISION_FINAL,
            payload={
                "meeting_session_id": self.session.id,
                "decided_by": "facilitator",
                "round_number": round_number,
                "decision": decision,
                "rationale": "Planner proposal accepted after critic review.",
                "dissenting_views": [],
                # A3: Decision provenance (Agent OS requirement)
                "lens_id": self.session.lens_id,
                "lens_hash": getattr(self, "_lens_hash", None),
                "intent_ids": getattr(self, "_active_intent_ids", []),
                "input_context_summary": {
                    "project_id": self.project_id,
                    "lens_preset": (
                        self._effective_lens.global_preset_name
                        if getattr(self, "_effective_lens", None)
                        else None
                    ),
                    "round_count": round_number,
                },
            },
        )

    def _emit_action_item(self, item: Dict[str, Any]) -> None:
        """Emit an ACTION_ITEM event."""
        self._emit_event(
            EventType.ACTION_ITEM,
            payload=item,
        )

    def _emit_round_event(self, round_number: int, status: str) -> None:
        """Emit a MEETING_ROUND lifecycle event."""
        self._emit_event(
            EventType.MEETING_ROUND,
            payload={
                "meeting_session_id": self.session.id,
                "round_number": round_number,
                "status": status,
                "speaker_order": ["facilitator", "planner", "critic"],
                "summary": f"Round {round_number} {status}",
            },
        )

    def _emit_minutes_message(self, minutes_md: str) -> None:
        """Emit a MESSAGE event containing the rendered meeting minutes."""
        self._emit_event(
            EventType.MESSAGE,
            payload={
                "message": minutes_md,
                "meeting_session_id": self.session.id,
                "is_meeting_minutes": True,
            },
            actor=EventActor.ASSISTANT,
            channel="meeting",
        )

    def _emit_event(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        actor: EventActor = EventActor.SYSTEM,
        channel: str = "meeting",
    ) -> None:
        """Create and persist a MindEvent, appending to the session event list."""
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            channel=channel,
            profile_id=self.profile_id,
            project_id=self.project_id,
            workspace_id=self.session.workspace_id,
            thread_id=self.thread_id or self.session.thread_id,
            event_type=event_type,
            payload=payload,
            entity_ids=[],
            metadata={"meeting_session_id": self.session.id},
        )
        self.store.create_event(event)
        self._events.append(event)
