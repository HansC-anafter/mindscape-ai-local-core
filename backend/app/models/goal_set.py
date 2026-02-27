"""
Goal Set schema for meeting governance.

Structured goal representation with four categories:
- What: milestones and deliverables
- How: methods, principles, and preferences
- Not: prohibitions and anti-patterns
- Metric: measurable success criteria and rubrics

Each clause carries an optional embedding vector for L3 semantic scoring.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class GoalCategory(str, Enum):
    """Goal clause category."""

    WHAT = "what"  # Milestones, deliverables, outcomes
    HOW = "how"  # Methods, principles, constraints
    NOT = "not"  # Prohibitions, anti-patterns, taboos
    METRIC = "metric"  # Measurable rubrics, scoring criteria


@dataclass
class GoalClause:
    """A single goal clause within a GoalSet."""

    id: str
    category: GoalCategory
    text: str
    weight: float = 1.0
    evidence_required: bool = False
    embedding: Optional[List[float]] = None  # L3: semantic vector
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new(
        category: GoalCategory,
        text: str,
        weight: float = 1.0,
        evidence_required: bool = False,
    ) -> "GoalClause":
        now = datetime.now(timezone.utc)
        return GoalClause(
            id=str(uuid.uuid4()),
            category=category,
            text=text,
            weight=weight,
            evidence_required=evidence_required,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "category": (
                self.category.value
                if isinstance(self.category, GoalCategory)
                else self.category
            ),
            "text": self.text,
            "weight": self.weight,
            "evidence_required": self.evidence_required,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.embedding is not None:
            result["embedding"] = self.embedding
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalClause":
        cat = data.get("category", "what")
        if isinstance(cat, str):
            cat = GoalCategory(cat)
        created = data.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        updated = data.get("updated_at")
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return cls(
            id=data["id"],
            category=cat,
            text=data["text"],
            weight=data.get("weight", 1.0),
            evidence_required=data.get("evidence_required", False),
            embedding=data.get("embedding"),
            metadata=data.get("metadata", {}),
            created_at=created or datetime.now(timezone.utc),
            updated_at=updated or datetime.now(timezone.utc),
        )


@dataclass
class GoalSet:
    """
    Structured goal set for a workspace or project.

    Contains clauses across four categories (What/How/Not/Metric).
    L3 scoring formulas operate on these clauses:
    - Progress = sim(extract, goal_what)
    - Violation = sim(extract, goal_not)
    """

    id: str
    workspace_id: str
    project_id: Optional[str] = None
    clauses: List[GoalClause] = field(default_factory=list)
    version: int = 1
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new(
        workspace_id: str,
        project_id: Optional[str] = None,
        clauses: Optional[List[GoalClause]] = None,
    ) -> "GoalSet":
        now = datetime.now(timezone.utc)
        return GoalSet(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=project_id,
            clauses=clauses or [],
            created_at=now,
            updated_at=now,
        )

    @property
    def goal_what(self) -> List[GoalClause]:
        return [c for c in self.clauses if c.category == GoalCategory.WHAT]

    @property
    def goal_how(self) -> List[GoalClause]:
        return [c for c in self.clauses if c.category == GoalCategory.HOW]

    @property
    def goal_not(self) -> List[GoalClause]:
        return [c for c in self.clauses if c.category == GoalCategory.NOT]

    @property
    def goal_metric(self) -> List[GoalClause]:
        return [c for c in self.clauses if c.category == GoalCategory.METRIC]

    def add_clause(self, clause: GoalClause) -> None:
        self.clauses.append(clause)
        self.updated_at = datetime.now(timezone.utc)

    def remove_clause(self, clause_id: str) -> bool:
        before = len(self.clauses)
        self.clauses = [c for c in self.clauses if c.id != clause_id]
        if len(self.clauses) < before:
            self.updated_at = datetime.now(timezone.utc)
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "clauses": [c.to_dict() for c in self.clauses],
            "version": self.version,
            "is_active": self.is_active,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalSet":
        created = data.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        updated = data.get("updated_at")
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return cls(
            id=data["id"],
            workspace_id=data["workspace_id"],
            project_id=data.get("project_id"),
            clauses=[GoalClause.from_dict(c) for c in data.get("clauses", [])],
            version=data.get("version", 1),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {}),
            created_at=created or datetime.now(timezone.utc),
            updated_at=updated or datetime.now(timezone.utc),
        )
