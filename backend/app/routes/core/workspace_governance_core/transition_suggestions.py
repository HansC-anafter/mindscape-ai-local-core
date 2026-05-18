from typing import List, Optional

from .schemas import (
    EvidenceCoverageSummary,
    MemoryEvidenceSummary,
    SuccessorDraftSuggestionSummary,
    TransitionCueSummary,
    TransitionReasonSuggestions,
    WorkspaceMemoryItemSummary,
)
from .serializers import _evidence_display_name, _select_primary_evidence


def _build_transition_cues(
    memory_item: WorkspaceMemoryItemSummary,
    evidence_links: List[MemoryEvidenceSummary],
    coverage: EvidenceCoverageSummary,
) -> List[TransitionCueSummary]:
    cues: List[TransitionCueSummary] = []
    has_operational_evidence = coverage.execution > 0 or coverage.governance > 0
    has_deliberation_evidence = coverage.deliberation > 0
    has_artifact_or_task_evidence = any(
        link.evidence_type
        in {"task_execution", "execution_trace", "stage_result", "artifact_result"}
        for link in evidence_links
    )
    has_decision_evidence = any(
        link.evidence_type
        in {"meeting_decision", "intent_log", "governance_decision", "lens_patch"}
        for link in evidence_links
    )

    if memory_item.lifecycle_status == "candidate":
        if has_deliberation_evidence and has_operational_evidence:
            cues.append(
                TransitionCueSummary(
                    id="verify-ready",
                    tone="positive",
                    title="Verification signal is available",
                    body=(
                        "This candidate is backed by both deliberation evidence and "
                        "downstream execution or governance receipts. Verify it when "
                        "the claim reflects the current working standard."
                    ),
                )
            )
        else:
            cues.append(
                TransitionCueSummary(
                    id="verify-hold",
                    tone="caution",
                    title="Hold as candidate until coverage improves",
                    body=(
                        "Keep this item in candidate state while additional "
                        "decisions, executions, or artifacts accumulate around the claim."
                    ),
                )
            )

    if memory_item.lifecycle_status == "active":
        cues.append(
            TransitionCueSummary(
                id="stale-usage",
                tone="neutral",
                title="Use stale for context drift",
                body=(
                    "Mark the item stale when the claim no longer matches the active "
                    "workspace context and no replacement claim is ready yet."
                ),
            )
        )
        if has_artifact_or_task_evidence or has_decision_evidence:
            cues.append(
                TransitionCueSummary(
                    id="supersede-usage",
                    tone="positive",
                    title="Supersede when a successor claim is ready",
                    body=(
                        "This item already has decision or execution evidence attached. "
                        "Create a successor when the current claim should remain visible "
                        "as history while a new operating claim takes over."
                    ),
                )
            )

    if coverage.support == 0 and coverage.derived > 0:
        cues.append(
            TransitionCueSummary(
                id="support-gap",
                tone="caution",
                title="Support evidence is still thin",
                body=(
                    "The current chain is dominated by derived receipts. Add or wait "
                    "for direct supporting evidence before promoting a weak claim."
                ),
            )
        )

    if not cues:
        cues.append(
            TransitionCueSummary(
                id="baseline",
                tone="neutral",
                title="Review the evidence chain before transitioning",
                body=(
                    "Use the evidence mix, recency, and projection history to decide "
                    "whether this claim should stay active, become stale, or move to a successor."
                ),
            )
        )
    return cues


def _build_successor_draft_suggestion(
    memory_item: WorkspaceMemoryItemSummary,
    evidence_links: List[MemoryEvidenceSummary],
    coverage: EvidenceCoverageSummary,
) -> Optional[SuccessorDraftSuggestionSummary]:
    if memory_item.lifecycle_status != "active":
        return None

    primary_evidence = _select_primary_evidence(evidence_links)
    primary_excerpt = (primary_evidence.excerpt or "").strip() if primary_evidence else ""
    primary_label = (
        _evidence_display_name(primary_evidence.evidence_type)
        if primary_evidence
        else "Evidence Chain"
    )
    claim = (
        primary_excerpt
        or memory_item.claim
        or memory_item.summary
        or "Refine the working claim based on the latest validated evidence."
    )
    title = (
        memory_item.title
        if "revision" in memory_item.title.lower()
        else f"{memory_item.title} Revision"
    )
    summary_parts = [
        f"Successor drafted from {primary_label.lower()}.",
        (
            f"Coverage: {coverage.deliberation} deliberation, "
            f"{coverage.execution} execution, {coverage.governance} governance."
        ),
    ]
    if primary_evidence and primary_evidence.evidence_id:
        summary_parts.append(f"Anchor evidence: {primary_evidence.evidence_id}.")

    return SuccessorDraftSuggestionSummary(
        title=title,
        claim=claim,
        summary=" ".join(summary_parts),
        primary_evidence_id=getattr(primary_evidence, "evidence_id", None),
        primary_evidence_type=getattr(primary_evidence, "evidence_type", None),
    )


def _build_transition_reason_suggestions(
    memory_item: WorkspaceMemoryItemSummary,
    primary_evidence: Optional[MemoryEvidenceSummary],
    coverage: EvidenceCoverageSummary,
) -> TransitionReasonSuggestions:
    anchor = (
        f"{_evidence_display_name(primary_evidence.evidence_type)} "
        f"{primary_evidence.evidence_id}"
        if primary_evidence
        else "the current evidence chain"
    )
    return TransitionReasonSuggestions(
        verify=(
            f"Verified after reviewing {anchor} with "
            f"{coverage.deliberation} deliberation signals and "
            f"{coverage.execution + coverage.governance} downstream execution or governance signals."
        ),
        stale=(
            f"Marked stale because the active workspace context moved beyond this claim "
            f"and no replacement was finalized from {anchor}."
        ),
        supersede=(
            f"Superseded after {anchor} established a newer operating claim "
            f"for {memory_item.title}."
        ),
    )
