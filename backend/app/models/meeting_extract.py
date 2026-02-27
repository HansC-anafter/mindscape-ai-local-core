"""
Meeting Extract schema for structured meeting output.

Extracts typed items (Decision, Action, Risk, Artifact, Assumption) from
meeting events. This is the X_t that L3 scoring formulas compare against
the GoalSet G to compute Progress and Violation scores.

Pipeline: Meeting Events -> LLM Summarizer -> MeetingExtract (typed items)
                                                    |
                                               (L3: embed + score against GoalSet)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ExtractType(str, Enum):
    """Type of extracted meeting item."""

    DECISION = "decision"  # Agreed-upon choices
    ACTION = "action"  # Next steps, tasks to do
    RISK = "risk"  # Identified risks, objections
    ARTIFACT = "artifact"  # Produced outputs (docs, PRs, files)
    ASSUMPTION = "assumption"  # Underlying assumptions


@dataclass
class MeetingExtractItem:
    """A single structured item extracted from meeting events."""

    id: str
    meeting_session_id: str
    extract_type: ExtractType
    content: str
    embedding: Optional[List[float]] = None  # L3: semantic vector for scoring
    source_event_ids: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    goal_clause_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    agent_id: Optional[str] = None  # Which agent produced this
    round_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new(
        meeting_session_id: str,
        extract_type: ExtractType,
        content: str,
        source_event_ids: Optional[List[str]] = None,
        evidence_refs: Optional[List[str]] = None,
        goal_clause_ids: Optional[List[str]] = None,
        confidence: float = 0.0,
        agent_id: Optional[str] = None,
        round_number: Optional[int] = None,
    ) -> "MeetingExtractItem":
        return MeetingExtractItem(
            id=str(uuid.uuid4()),
            meeting_session_id=meeting_session_id,
            extract_type=extract_type,
            content=content,
            source_event_ids=source_event_ids or [],
            evidence_refs=evidence_refs or [],
            goal_clause_ids=goal_clause_ids or [],
            confidence=confidence,
            agent_id=agent_id,
            round_number=round_number,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "meeting_session_id": self.meeting_session_id,
            "extract_type": (
                self.extract_type.value
                if isinstance(self.extract_type, ExtractType)
                else self.extract_type
            ),
            "content": self.content,
            "source_event_ids": self.source_event_ids,
            "evidence_refs": self.evidence_refs,
            "goal_clause_ids": self.goal_clause_ids,
            "confidence": self.confidence,
            "agent_id": self.agent_id,
            "round_number": self.round_number,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
        if self.embedding is not None:
            result["embedding"] = self.embedding
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeetingExtractItem":
        et = data.get("extract_type", "decision")
        if isinstance(et, str):
            et = ExtractType(et)
        created = data.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return cls(
            id=data["id"],
            meeting_session_id=data["meeting_session_id"],
            extract_type=et,
            content=data["content"],
            embedding=data.get("embedding"),
            source_event_ids=data.get("source_event_ids", []),
            evidence_refs=data.get("evidence_refs", []),
            goal_clause_ids=data.get("goal_clause_ids", []),
            confidence=data.get("confidence", 0.0),
            agent_id=data.get("agent_id"),
            round_number=data.get("round_number"),
            metadata=data.get("metadata", {}),
            created_at=created or datetime.now(timezone.utc),
        )


@dataclass
class MeetingExtract:
    """
    One meeting's full structured extract (the X_t).

    This is the primary input to L3 scoring:
    - Progress(X_t, G) = sum over items scored against GoalSet
    - Violation(X_t, G_not) = sum over items scored against prohibitions
    """

    id: str
    meeting_session_id: str
    items: List[MeetingExtractItem] = field(default_factory=list)
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    goal_set_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new(
        meeting_session_id: str,
        items: Optional[List[MeetingExtractItem]] = None,
        goal_set_id: Optional[str] = None,
        state_snapshot: Optional[Dict[str, Any]] = None,
    ) -> "MeetingExtract":
        return MeetingExtract(
            id=str(uuid.uuid4()),
            meeting_session_id=meeting_session_id,
            items=items or [],
            goal_set_id=goal_set_id,
            state_snapshot=state_snapshot or {},
        )

    @property
    def decisions(self) -> List[MeetingExtractItem]:
        return [i for i in self.items if i.extract_type == ExtractType.DECISION]

    @property
    def actions(self) -> List[MeetingExtractItem]:
        return [i for i in self.items if i.extract_type == ExtractType.ACTION]

    @property
    def risks(self) -> List[MeetingExtractItem]:
        return [i for i in self.items if i.extract_type == ExtractType.RISK]

    @property
    def artifacts(self) -> List[MeetingExtractItem]:
        return [i for i in self.items if i.extract_type == ExtractType.ARTIFACT]

    @property
    def assumptions(self) -> List[MeetingExtractItem]:
        return [i for i in self.items if i.extract_type == ExtractType.ASSUMPTION]

    @property
    def items_with_evidence(self) -> List[MeetingExtractItem]:
        return [i for i in self.items if i.evidence_refs]

    @property
    def evidence_density(self) -> float:
        """Fraction of decision/action items that have evidence."""
        actionable = [
            i
            for i in self.items
            if i.extract_type in (ExtractType.DECISION, ExtractType.ACTION)
        ]
        if not actionable:
            return 0.0
        return len([i for i in actionable if i.evidence_refs]) / len(actionable)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "meeting_session_id": self.meeting_session_id,
            "items": [i.to_dict() for i in self.items],
            "state_snapshot": self.state_snapshot,
            "goal_set_id": self.goal_set_id,
            "evidence_density": self.evidence_density,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeetingExtract":
        created = data.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return cls(
            id=data["id"],
            meeting_session_id=data["meeting_session_id"],
            items=[MeetingExtractItem.from_dict(i) for i in data.get("items", [])],
            state_snapshot=data.get("state_snapshot", {}),
            goal_set_id=data.get("goal_set_id"),
            metadata=data.get("metadata", {}),
            created_at=created or datetime.now(timezone.utc),
        )
