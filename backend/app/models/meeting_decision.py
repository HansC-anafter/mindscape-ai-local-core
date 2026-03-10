"""
Meeting decision model for structured decision tracking.

Extracts decisions, action items, blockers, and insights from meeting
sessions into queryable row-level records for cross-session traceability.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class MeetingDecision:
    """Structured decision record from a meeting session."""

    id: str
    session_id: str
    workspace_id: str
    category: str  # "action" | "decision" | "blocker" | "insight"
    content: str
    status: str = "pending"  # "pending" | "dispatched" | "resolved" | "cancelled"
    resolved_by_task_id: Optional[str] = None
    source_action_item: Optional[Dict[str, Any]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def from_action_item(
        action_item: Dict[str, Any],
        session_id: str,
        workspace_id: str,
    ) -> "MeetingDecision":
        """Create from a meeting action_item dict."""
        return MeetingDecision(
            id=str(uuid.uuid4()),
            session_id=session_id,
            workspace_id=workspace_id,
            category=action_item.get("category", "action"),
            content=(
                action_item.get("description")
                or action_item.get("task")
                or action_item.get("title")
                or str(action_item)
            ),
            status="dispatched" if action_item.get("landing_status") else "pending",
            source_action_item=action_item,
        )

    @staticmethod
    def extract_from_session(
        session: Any,
    ) -> List["MeetingDecision"]:
        """Extract decisions from a MeetingSession's action_items."""
        session_id = getattr(session, "id", "") or ""
        workspace_id = getattr(session, "workspace_id", "") or ""
        action_items = getattr(session, "action_items", []) or []

        decisions = []
        for item in action_items:
            if isinstance(item, dict):
                decisions.append(
                    MeetingDecision.from_action_item(item, session_id, workspace_id)
                )
        return decisions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "workspace_id": self.workspace_id,
            "category": self.category,
            "content": self.content,
            "status": self.status,
            "resolved_by_task_id": self.resolved_by_task_id,
            "source_action_item": self.source_action_item,
            "created_at": self.created_at.isoformat(),
        }
