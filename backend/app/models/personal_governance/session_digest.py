"""
SessionDigest — unified cross-source summary format (L1→L2 bridge).

Contract defined in ADR-001 v2, §Gap 1.
All signal sources (meeting close, chat_capture session close, file uploads)
produce digests in this format for unified semantic retrieval in L2.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SessionDigest:
    """Unified cross-source summary for L2 semantic memory."""

    # --- Identity ---
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_type: str = (
        ""  # "meeting" | "chat_capture" | "file_upload" | "playbook_complete"
    )
    source_id: str = ""  # meeting_session.id | chat_capture_session.id | ...
    source_time_start: Optional[datetime] = None
    source_time_end: Optional[datetime] = None
    digest_version: str = "1.0"

    # --- Scope ---
    owner_profile_id: str = ""
    workspace_refs: List[str] = field(default_factory=list)
    project_refs: List[str] = field(default_factory=list)
    participants: List[str] = field(default_factory=list)

    # --- Content ---
    summary_md: str = ""  # ≤500 tokens structured summary
    claims: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)

    # --- Embedding ---
    embedding_text: str = ""  # concatenated searchable text
    # embedding vector stored in memory_embeddings table (vectors DB)

    # --- Provenance ---
    provenance_refs: List[str] = field(default_factory=list)
    sensitivity: str = "private"  # "public" | "private" | "confidential"

    # --- Metadata ---
    created_at: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_meeting_session(
        session: Any,
        workspace: Any,
        profile_id: str,
    ) -> "SessionDigest":
        """Create digest from a closed MeetingSession."""
        action_items = getattr(session, "action_items", []) or []
        decisions_raw = getattr(session, "decisions", []) or []
        minutes = getattr(session, "minutes_md", "") or ""

        actions = [
            {
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "priority": a.get("priority", "medium"),
                "status": a.get("landing_status", "pending"),
            }
            for a in action_items[:10]
        ]

        return SessionDigest(
            source_type="meeting",
            source_id=getattr(session, "id", ""),
            source_time_start=getattr(session, "started_at", None),
            source_time_end=getattr(session, "ended_at", None),
            owner_profile_id=profile_id,
            workspace_refs=[getattr(session, "workspace_id", "")],
            project_refs=[p for p in [getattr(session, "project_id", None)] if p],
            participants=["user", "planner", "critic", "facilitator"],
            summary_md=minutes[:2000],  # cap raw storage
            actions=actions,
            decisions=[{"event_id": d} for d in decisions_raw[:10]],
            embedding_text=_build_embedding_text(minutes, actions),
            provenance_refs=[f"meeting_session:{getattr(session, 'id', '')}"],
        )



def _build_embedding_text(minutes: str, actions: List[Dict]) -> str:
    """Build concatenated searchable text for embedding."""
    parts = []
    if minutes:
        parts.append(minutes[:1000])
    for a in actions[:5]:
        title = a.get("title", "")
        desc = a.get("description", "")
        if title:
            parts.append(f"Action: {title}")
        if desc:
            parts.append(desc[:200])
    return "\n".join(parts)[:2000]
