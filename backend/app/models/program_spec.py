"""
Program Spec — structured program output from Layer 1 deliberation.

ProgramSpec is the final artifact produced by the Program Synthesizer
(formerly Executor) role.  It is the bridge between Layer 1 (deliberation)
and Layer 2 (decomposition / dispatch).

Lifecycle:
    ProgramDraft → CoverageAuditor → ProgramSpec → TaskDecomposer → TaskIR DAG
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.models.request_contract import ScaleEstimate


class Workstream(BaseModel):
    """A logical stream of work within a ProgramSpec."""

    id: str = Field(..., description="Stable workstream ID")
    name: str = Field(default="", description="e.g. 'Research Stream'")
    description: str = Field(default="")
    estimated_units: int = Field(default=1, ge=1, description="e.g. 10 papers")
    unit_template: Optional[str] = Field(
        default=None,
        description="e.g. 'fetch → summarize' pattern",
    )
    eligible_engines: List[str] = Field(
        default_factory=list,
        description="e.g. ['playbook:research_synthesis', 'tool:frontier_research']",
    )


class Milestone(BaseModel):
    """A milestone that gates progress across workstreams."""

    id: str = Field(..., description="Stable milestone ID")
    name: str = Field(default="")
    depends_on_streams: List[str] = Field(
        default_factory=list,
        description="Workstream IDs that must complete first",
    )
    deliverables: List[str] = Field(
        default_factory=list,
        description="Deliverable IDs produced at this milestone",
    )


class ProgramSpec(BaseModel):
    """Layer 1 final output — verifiable, decomposable, dispatchable.

    This replaces the flat list of action items with a structured program
    that can be hierarchically decomposed by TaskDecomposer.
    """

    workstreams: List[Workstream] = Field(default_factory=list)
    milestones: List[Milestone] = Field(default_factory=list)
    dependency_graph: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="stream_id → depends_on stream_ids",
    )
    target_outputs: List[str] = Field(
        default_factory=list,
        description="Expected final deliverable names",
    )
    scale: ScaleEstimate = Field(default=ScaleEstimate.STANDARD)
    coverage_snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="CoverageMatrix snapshot at synthesis time",
    )
