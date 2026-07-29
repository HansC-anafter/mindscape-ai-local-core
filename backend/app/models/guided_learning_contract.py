"""Typed bounded learning context carried by a Meeting answer request."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class GuidedLearningRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    route_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    label: str = Field(min_length=1, max_length=240)
    route_kind: Literal[
        "continue",
        "prerequisite",
        "branch",
        "cross_domain",
        "review",
    ]


class GuidedLearningContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    current_question_id: str = Field(min_length=1, max_length=256)
    current_checkpoint_id: Optional[str] = Field(
        default=None,
        max_length=256,
    )
    current_competency_key: Optional[str] = Field(
        default=None,
        max_length=256,
    )
    belief_uncertainty: float = Field(default=1.0, ge=0.0, le=1.0)
    due_state: Literal[
        "not_due",
        "review_due",
        "retention_due",
        "material_change_revalidation_required",
    ] = "not_due"
    session_state: Literal[
        "explore",
        "diagnose",
        "counterexample",
        "transfer",
        "teach_back",
    ] = "explore"
    why_this_next: str = Field(min_length=1, max_length=1000)
    next_routes: List[GuidedLearningRoute] = Field(
        default_factory=list,
        max_length=3,
    )


__all__ = ["GuidedLearningContext", "GuidedLearningRoute"]
