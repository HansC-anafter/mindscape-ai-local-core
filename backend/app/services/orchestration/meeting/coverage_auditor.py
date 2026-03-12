"""
Coverage Auditor — deterministic contract reference validation service.

v3.1: This is a **service**, NOT a meeting agent. It does not call LLM
and does not participate in model routing. If LLM-assisted coverage
review is needed in the future, create a separate CoverageReviewer agent.

Validates that a ProgramDraft's workstreams fully cover the deliverables
defined in a RequestContract using deterministic ID matching only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CoverageEntry(BaseModel):
    """Coverage status for a single deliverable."""

    deliverable_id: str = Field(..., description="Contract reference ID")
    deliverable_name: str = Field(default="")
    quantity_required: int = Field(default=1)
    quantity_covered: int = Field(default=0)
    covered_by: List[str] = Field(
        default_factory=list,
        description="Workstream IDs that PRODUCE this deliverable",
    )
    acceptance_mapped: bool = Field(
        default=False,
        description="At least one workstream reviews this deliverable",
    )
    gap: Optional[str] = Field(
        default=None,
        description="Human-readable gap description (None = fully covered)",
    )


class OwnershipClaim(BaseModel):
    """A single workstream's claim on a deliverable."""

    workstream_id: str
    ownership_type: str = Field(..., description="'produces' | 'reviews' | 'consumes'")


class OwnershipConflict(BaseModel):
    """v3.1: Distinguishes legitimate multi-reference from true conflicts.

    is_conflict is True ONLY when >1 workstream claims PRODUCES for the
    same deliverable.  Review and consume references are normal.
    """

    deliverable_id: str
    claimants: List[OwnershipClaim] = Field(default_factory=list)
    is_conflict: bool = Field(
        default=False,
        description="True only when >1 PRODUCES claim",
    )


class CoverageMatrix(BaseModel):
    """Deterministic contract reference validation result."""

    entries: List[CoverageEntry] = Field(default_factory=list)
    coverage_pass: bool = Field(default=False)
    coverage_pct: float = Field(default=0.0)
    orphan_deliverables: List[str] = Field(
        default_factory=list,
        description="Deliverable IDs not produced by any workstream",
    )
    ownership_conflicts: List[OwnershipConflict] = Field(
        default_factory=list,
        description="Deliverables with >1 PRODUCES claim",
    )

    def gap_summary(self) -> str:
        """One-line summary of coverage gaps for critic feedback."""
        gaps = [e for e in self.entries if e.gap]
        if not gaps and not self.orphan_deliverables:
            return "Full coverage"
        parts = []
        for e in gaps:
            parts.append(f"{e.deliverable_id}: {e.gap}")
        if self.orphan_deliverables:
            parts.append(f"Orphans: {self.orphan_deliverables}")
        return "; ".join(parts)


class WorkstreamDraft(BaseModel):
    """A workstream in the planner's intermediate ProgramDraft.

    v3.1: Three types of deliverable references:
    - produces: this stream is responsible for creating the deliverable
    - reviews:  this stream QA/reviews the deliverable
    - consumes: this stream uses another stream's output
    """

    id: str
    name: str = ""
    produces_deliverables: List[str] = Field(
        default_factory=list,
        description="Deliverable IDs this stream produces",
    )
    reviews_deliverables: List[str] = Field(
        default_factory=list,
        description="Deliverable IDs this stream reviews",
    )
    consumes_deliverables: List[str] = Field(
        default_factory=list,
        description="Deliverable IDs this stream consumes from others",
    )
    estimated_units: int = Field(default=1)
    acceptance_refs: List[str] = Field(
        default_factory=list,
        description="Contract acceptance criteria IDs",
    )
    depends_on: List[str] = Field(default_factory=list)

    @property
    def all_referenced_deliverables(self) -> List[str]:
        return list(
            set(
                self.produces_deliverables
                + self.reviews_deliverables
                + self.consumes_deliverables
            )
        )


class ProgramDraft(BaseModel):
    """Planner's intermediate output structure.

    Workstreams must explicitly annotate deliverable references.
    CoverageAuditor only does ID matching, no semantic guessing.
    v3.1: Distinguishes produces / reviews / consumes reference types.
    """

    workstreams: List[WorkstreamDraft] = Field(default_factory=list)
    total_estimated_tasks: int = Field(default=0)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CoverageAuditor:
    """Contract Reference Validation — deterministic service, no LLM.

    v3.1: Explicitly a service, not a meeting agent. No model routing.
    Asks "are D1, D2, D3 explicitly covered by ProgramDraft?" — not
    "are 'IG post' and 'social post' the same thing?".
    """

    def audit(
        self,
        contract: Any,  # RequestContract
        draft: ProgramDraft,
    ) -> CoverageMatrix:
        """Run deterministic coverage validation.

        Args:
            contract: RequestContract with deliverables[].id
            draft: ProgramDraft with workstreams

        Returns:
            CoverageMatrix with pass/fail, gaps, and ownership conflicts.
        """
        entries: List[CoverageEntry] = []
        all_covered_ids: set = set()

        for d in contract.deliverables:
            # Coverage = at least one workstream PRODUCES this deliverable
            producers = [
                ws for ws in draft.workstreams if d.id in ws.produces_deliverables
            ]
            qty_covered = sum(ws.estimated_units for ws in producers)
            if producers:
                all_covered_ids.add(d.id)

            # Acceptance mapping = any workstream REVIEWS this deliverable
            reviewers = [
                ws for ws in draft.workstreams if d.id in ws.reviews_deliverables
            ]

            entries.append(
                CoverageEntry(
                    deliverable_id=d.id,
                    deliverable_name=d.name,
                    quantity_required=d.quantity,
                    quantity_covered=qty_covered,
                    covered_by=[ws.id for ws in producers],
                    acceptance_mapped=len(reviewers) > 0,
                    gap=(
                        f"Missing {d.quantity - qty_covered} units"
                        if qty_covered < d.quantity
                        else None
                    ),
                )
            )

        orphans = [d.id for d in contract.deliverables if d.id not in all_covered_ids]

        # v3.1: Ownership conflict = same deliverable PRODUCED by >1 stream
        ownership_conflicts: List[OwnershipConflict] = []
        producer_map: Dict[str, List[str]] = {}
        for ws in draft.workstreams:
            for did in ws.produces_deliverables:
                producer_map.setdefault(did, []).append(ws.id)
        for did, prod_ids in producer_map.items():
            if len(prod_ids) > 1:
                claims = [
                    OwnershipClaim(workstream_id=wid, ownership_type="produces")
                    for wid in prod_ids
                ]
                ownership_conflicts.append(
                    OwnershipConflict(
                        deliverable_id=did,
                        claimants=claims,
                        is_conflict=True,
                    )
                )

        coverage_pass = all(e.gap is None for e in entries) and not orphans
        total_req = max(sum(e.quantity_required for e in entries), 1)
        coverage_pct = (
            sum(min(e.quantity_covered, e.quantity_required) for e in entries)
            / total_req
        )

        return CoverageMatrix(
            entries=entries,
            coverage_pass=coverage_pass,
            coverage_pct=coverage_pct,
            orphan_deliverables=orphans,
            ownership_conflicts=ownership_conflicts,
        )
