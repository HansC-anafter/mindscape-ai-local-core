"""Private drift-report helpers for EGBOrchestrator."""

import logging
from typing import Optional

from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.drift_report import RunDriftReport
from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.services.baseline_picker import BaselinePicker, BaselineStrategy

logger = logging.getLogger(__name__)


def build_baseline_picker(orchestrator) -> BaselinePicker:
    """Create the existing baseline picker without owning route or DB setup."""
    return BaselinePicker(
        trace_linker=orchestrator.trace_linker,
        evidence_cache=orchestrator._evidence_cache,
        orchestrator=orchestrator,
    )


async def pick_last_success_baseline(
    orchestrator,
    correlation_ids: CorrelationIds,
    current_run_id: str,
):
    """Pick the current last-success baseline with the existing constraints."""
    baseline_picker = build_baseline_picker(orchestrator)
    return await baseline_picker.pick_baseline(
        intent_id=correlation_ids.intent_id,
        current_policy_version=correlation_ids.policy_version or "default",
        strategy=BaselineStrategy.LAST_SUCCESS,
        allow_cross_version=False,
        current_run_id=current_run_id,
    )


async def get_cached_or_rebuilt_evidence(
    orchestrator,
    run_id: str,
    correlation_ids: CorrelationIds,
) -> Optional[StructuredEvidence]:
    """Return evidence from cache or rebuild it through the public orchestrator."""
    evidence = orchestrator._evidence_cache.get(run_id)
    if evidence:
        return evidence

    evidence = await orchestrator._rebuild_evidence(run_id, correlation_ids)
    if evidence:
        orchestrator._evidence_cache[run_id] = evidence
    return evidence


async def get_baseline_evidence(
    orchestrator,
    baseline_run_id: str,
) -> Optional[StructuredEvidence]:
    """Load baseline evidence from cache or rebuild it by run id."""
    baseline_evidence = orchestrator._evidence_cache.get(baseline_run_id)
    if baseline_evidence:
        return baseline_evidence

    baseline_correlation_ids = await orchestrator.trace_linker.get_run_by_id(
        baseline_run_id
    )
    if not baseline_correlation_ids:
        return None

    baseline_evidence = await orchestrator._rebuild_evidence(
        baseline_run_id, baseline_correlation_ids
    )
    if baseline_evidence:
        orchestrator._evidence_cache[baseline_run_id] = baseline_evidence
    return baseline_evidence


def compute_semantic_diff_pointers(
    current_evidence: StructuredEvidence,
    baseline_evidence: StructuredEvidence,
) -> list[str]:
    """Return keys whose semantic hash differs between current and baseline."""
    if (
        not current_evidence.key_fields_hash_map
        or not baseline_evidence.key_fields_hash_map
    ):
        return []

    current_keys = set(current_evidence.key_fields_hash_map.keys())
    baseline_keys = set(baseline_evidence.key_fields_hash_map.keys())
    semantic_diff_pointers = []
    for key in current_keys | baseline_keys:
        if current_evidence.key_fields_hash_map.get(
            key
        ) != baseline_evidence.key_fields_hash_map.get(key):
            semantic_diff_pointers.append(key)
    return semantic_diff_pointers


def build_run_drift_report(
    *,
    run_id: str,
    baseline_run_id: str,
    correlation_ids: CorrelationIds,
    drift_scores,
    attributions,
    semantic_diff_pointers: list[str],
) -> RunDriftReport:
    """Build the RunDriftReport with the existing field mapping."""
    return RunDriftReport(
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        intent_id=correlation_ids.intent_id,
        workspace_id=correlation_ids.workspace_id,
        drift_scores=drift_scores,
        drift_explanations=attributions,
        semantic_diff_pointers=semantic_diff_pointers,
    )


async def get_drift_report_for_run(
    orchestrator,
    run_id: str,
    baseline_run_id: Optional[str] = None,
) -> Optional[RunDriftReport]:
    """Run the existing drift-report flow for the public orchestrator method."""
    correlation_ids = await orchestrator.trace_linker.get_run_by_id(run_id)
    if not correlation_ids:
        logger.warning(f"EGBOrchestrator: Run {run_id} not found")
        return None

    current_evidence = await get_cached_or_rebuilt_evidence(
        orchestrator, run_id, correlation_ids
    )
    if not current_evidence:
        logger.warning(f"EGBOrchestrator: Failed to rebuild evidence for run {run_id}")
        return None

    if not baseline_run_id:
        baseline_selection = await pick_last_success_baseline(
            orchestrator, correlation_ids, run_id
        )
        if not baseline_selection.has_baseline:
            logger.info(f"EGBOrchestrator: No baseline found for run {run_id}")
            return None
        baseline_run_id = baseline_selection.baseline_run_id

    baseline_evidence = await get_baseline_evidence(orchestrator, baseline_run_id)
    if not baseline_evidence:
        logger.warning(
            f"EGBOrchestrator: Baseline evidence for {baseline_run_id} not found"
        )
        return None

    drift_scores = await orchestrator.drift_scorer.compute_drift(
        current=current_evidence,
        baseline=baseline_evidence,
        store=orchestrator.store,
    )
    attributions = await orchestrator.policy_attributor.attribute_drift(
        drift_scores=drift_scores,
        current_evidence=current_evidence,
        baseline_evidence=baseline_evidence,
    )
    drift_report = build_run_drift_report(
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        correlation_ids=correlation_ids,
        drift_scores=drift_scores,
        attributions=attributions,
        semantic_diff_pointers=compute_semantic_diff_pointers(
            current_evidence, baseline_evidence
        ),
    )

    if orchestrator.store:
        await orchestrator.store.save_drift_report(drift_report)

    return drift_report
