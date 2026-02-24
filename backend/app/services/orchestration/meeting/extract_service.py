"""
Meeting extract service — events to MeetingExtract pipeline.

Scans meeting events (AGENT_TURN, DECISION_FINAL, PLANNER_PROPOSAL,
CRITIC_NOTE) and produces a typed MeetingExtract with items classified
by ExtractType (decision, action, risk, artifact, assumption).

Matches MeetingExtract/MeetingExtractItem model contracts exactly:
  - ExtractType enum (not ExtractItemType)
  - meeting_session_id on items
  - source_event_ids as List[str]
  - agent_id (not source_agent_role)

L2 Bridge pipeline: MeetingEngine events -> MeetingExtract -> GoalLinking
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any, Dict

from backend.app.models.meeting_extract import (
    MeetingExtract,
    MeetingExtractItem,
    ExtractType,
)

logger = logging.getLogger(__name__)

# Mapping from event type to extract type
_EVENT_TYPE_MAP = {
    "DECISION_FINAL": ExtractType.DECISION,
}

# Mapping from agent role to extract type
_AGENT_ROLE_MAP = {
    "planner": ExtractType.ACTION,
    "critic": ExtractType.RISK,
    "executor": ExtractType.ACTION,
    "facilitator": ExtractType.DECISION,
}


class MeetingExtractService:
    """Extract structured items from raw meeting events.

    Usage:
        service = MeetingExtractService()
        extract = service.extract_from_events(
            meeting_session_id="...",
            events=events,
        )
        # Persist via store:
        # extract_store.create(extract)
    """

    def extract_from_events(
        self,
        meeting_session_id: str,
        events: List[Any],
        goal_set_id: Optional[str] = None,
        state_snapshot: Optional[Dict[str, Any]] = None,
    ) -> MeetingExtract:
        """Process meeting events into a typed MeetingExtract.

        Args:
            meeting_session_id: Session that produced these events.
            events: List of MindEvent objects from meeting lifecycle.
            goal_set_id: Optional GoalSet association.
            state_snapshot: Optional state_snapshot at extraction time.

        Returns:
            MeetingExtract with classified items.
        """
        items: List[MeetingExtractItem] = []

        for event in events:
            payload = getattr(event, "payload", {}) or {}
            event_type_str = self._get_event_type_str(event)

            # Skip events not from this session
            session_id_in_payload = payload.get("meeting_session_id")
            if session_id_in_payload and session_id_in_payload != meeting_session_id:
                continue

            item = self._classify_event(
                event, event_type_str, payload, meeting_session_id
            )
            if item:
                items.append(item)

        extract = MeetingExtract(
            id=str(uuid.uuid4()),
            meeting_session_id=meeting_session_id,
            items=items,
            state_snapshot=state_snapshot or {},
            goal_set_id=goal_set_id,
            created_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Extracted %d items from %d events for session %s "
            "(decisions=%d, actions=%d, risks=%d)",
            len(items),
            len(events),
            meeting_session_id,
            sum(1 for i in items if i.extract_type == ExtractType.DECISION),
            sum(1 for i in items if i.extract_type == ExtractType.ACTION),
            sum(1 for i in items if i.extract_type == ExtractType.RISK),
        )

        return extract

    def _classify_event(
        self,
        event: Any,
        event_type_str: str,
        payload: Dict[str, Any],
        meeting_session_id: str,
    ) -> Optional[MeetingExtractItem]:
        """Classify a single event into an extract item."""
        event_id = getattr(event, "id", None)

        # DECISION_FINAL events become decisions
        if event_type_str in _EVENT_TYPE_MAP:
            content = payload.get("decision") or payload.get("content", "")
            if not content:
                return None
            return MeetingExtractItem(
                id=str(uuid.uuid4()),
                meeting_session_id=meeting_session_id,
                extract_type=_EVENT_TYPE_MAP[event_type_str],
                content=str(content),
                source_event_ids=[event_id] if event_id else [],
                evidence_refs=payload.get("evidence_refs", []),
                confidence=1.0,
                agent_id=payload.get("decided_by"),
                round_number=payload.get("round_number"),
            )

        # AGENT_TURN events classified by role
        if event_type_str == "AGENT_TURN":
            agent_role = payload.get("agent_role", "")
            extract_type = _AGENT_ROLE_MAP.get(agent_role)
            if not extract_type:
                return None
            content = payload.get("content", "")
            if not content:
                return None
            return MeetingExtractItem(
                id=str(uuid.uuid4()),
                meeting_session_id=meeting_session_id,
                extract_type=extract_type,
                content=str(content)[:500],
                source_event_ids=[event_id] if event_id else [],
                confidence=0.8,
                agent_id=payload.get("agent_id"),
                round_number=payload.get("round_number"),
            )

        return None

    @staticmethod
    def _get_event_type_str(event: Any) -> str:
        """Get event type as string."""
        et = getattr(event, "event_type", None)
        if et is None:
            return ""
        return et.value if hasattr(et, "value") else str(et)
