"""Private process/rebuild helpers for EGBOrchestrator."""

import logging
from typing import Optional

from backend.app.egb.components.governance_tuner import GovernanceSettings
from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.services.egb_orchestrator_drift import (
    build_run_drift_report,
    compute_semantic_diff_pointers,
    get_baseline_evidence,
    pick_last_success_baseline,
)

logger = logging.getLogger(__name__)


async def apply_process_drift_and_prescription(
    orchestrator,
    result,
    correlation_ids: CorrelationIds,
    evidence: StructuredEvidence,
    current_settings: Optional[GovernanceSettings] = None,
) -> None:
    """Apply the existing baseline, drift, attribution, and tuning sub-flow."""
    baseline_selection = await pick_last_success_baseline(
        orchestrator,
        correlation_ids,
        correlation_ids.run_id,
    )
    if not baseline_selection.has_baseline:
        return

    baseline_run_id = baseline_selection.baseline_run_id
    baseline_evidence = await get_baseline_evidence(orchestrator, baseline_run_id)
    if not baseline_evidence:
        return

    drift_scores = await orchestrator.drift_scorer.compute_drift(
        current=evidence,
        baseline=baseline_evidence,
        store=orchestrator.store,
    )
    attributions = await orchestrator.policy_attributor.attribute_drift(
        drift_scores=drift_scores,
        current_evidence=evidence,
        baseline_evidence=baseline_evidence,
    )
    result.drift_report = build_run_drift_report(
        run_id=correlation_ids.run_id,
        baseline_run_id=baseline_run_id,
        correlation_ids=correlation_ids,
        drift_scores=drift_scores,
        attributions=attributions,
        semantic_diff_pointers=compute_semantic_diff_pointers(
            evidence, baseline_evidence
        ),
    )

    settings = current_settings or GovernanceSettings()
    result.prescription = await orchestrator.governance_tuner.generate_prescription(
        drift_report=result.drift_report,
        attribution=attributions,
        current_settings=settings,
    )


async def rebuild_evidence(
    orchestrator,
    run_id: str,
    correlation_ids: CorrelationIds,
) -> Optional[StructuredEvidence]:
    """Rebuild evidence from Langfuse while preserving existing fallbacks."""
    if not orchestrator.langfuse_adapter or not orchestrator.langfuse_adapter._client:
        logger.warning(
            "EGBOrchestrator: No langfuse_adapter, trying to load evidence from store"
        )
        if orchestrator.store:
            logger.warning(
                "EGBOrchestrator: Store does not support loading evidence yet"
            )
        return None

    try:
        langfuse_trace = await orchestrator.langfuse_adapter.get_trace(run_id)
        if not langfuse_trace:
            logger.warning(f"EGBOrchestrator: Trace {run_id} not found in Langfuse")
            if orchestrator.store:
                logger.warning(
                    "EGBOrchestrator: Store does not support loading evidence yet"
                )
            return None

        from backend.app.egb.integrations.trace_normalizer import TraceNormalizer

        normalizer = TraceNormalizer()
        normalization_result = normalizer.normalize(langfuse_trace, run_id=run_id)

        if not normalization_result.success:
            logger.warning(
                f"EGBOrchestrator: Failed to normalize trace {run_id}: {normalization_result.error}"
            )
            if orchestrator.store:
                logger.warning(
                    "EGBOrchestrator: Store does not support loading evidence yet"
                )
            return None

        evidence = await orchestrator.evidence_reducer.reduce_trace(
            trace=normalization_result.trace_graph,
            correlation_ids=correlation_ids,
        )

        logger.info(f"EGBOrchestrator: Rebuilt evidence for run {run_id}")
        return evidence

    except Exception as e:
        logger.error(f"EGBOrchestrator: Failed to rebuild evidence for run {run_id}: {e}")
        if orchestrator.store:
            logger.warning(
                "EGBOrchestrator: Store does not support loading evidence yet"
            )
        return None
