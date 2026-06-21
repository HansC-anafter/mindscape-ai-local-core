"""
EGB orchestrator.

Coordinates EGB components while keeping route, store, and Langfuse resource
ownership outside the private helper seams.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.trace.trace_schema import TraceGraph
from backend.app.egb.components.drift_scorer import DriftScorer
from backend.app.egb.components.evidence_reducer import EvidenceReducer
from backend.app.egb.components.governance_tuner import (
    GovernanceSettings,
    GovernanceTuner,
)
from backend.app.egb.components.lens_explainer import LensExplainer
from backend.app.egb.components.policy_attributor import PolicyAttributor
from backend.app.egb.components.trace_linker import TraceLinker
from backend.app.egb.schemas.correlation_ids import CorrelationIds
from backend.app.egb.schemas.drift_report import RunDriftReport
from backend.app.egb.schemas.evidence_profile import IntentEvidenceProfile
from backend.app.egb.schemas.governance_prescription import GovernancePrescription
from backend.app.egb.schemas.run_outcome import RunOutcome, determine_run_outcome
from backend.app.egb.schemas.structured_evidence import StructuredEvidence
from backend.app.egb.services.egb_orchestrator_drift import get_drift_report_for_run
from backend.app.egb.services.egb_orchestrator_process import (
    apply_process_drift_and_prescription,
    rebuild_evidence,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


@dataclass
class EGBProcessResult:
    """Result of processing one EGB run."""

    correlation_ids: CorrelationIds
    structured_evidence: Optional[StructuredEvidence] = None
    drift_report: Optional[RunDriftReport] = None
    prescription: Optional[GovernancePrescription] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class EGBOrchestrator:
    """
    Public EGB orchestration facade.

    The class remains the single route-facing entry point. Private helper seams
    own drift/report assembly and evidence rebuild steps without creating DB
    sessions, route dependencies, workers, queues, or polling loops.
    """

    def __init__(
        self,
        trace_linker: Optional[TraceLinker] = None,
        evidence_reducer: Optional[EvidenceReducer] = None,
        drift_scorer: Optional[DriftScorer] = None,
        policy_attributor: Optional[PolicyAttributor] = None,
        lens_explainer: Optional[LensExplainer] = None,
        governance_tuner: Optional[GovernanceTuner] = None,
        langfuse_adapter=None,
        store=None,
    ):
        """Initialize the orchestrator and keep injected resource owners."""
        self.store = store
        self.trace_linker = trace_linker or TraceLinker(store=store)
        self.evidence_reducer = evidence_reducer or EvidenceReducer()
        self.drift_scorer = drift_scorer or DriftScorer()
        self.policy_attributor = policy_attributor or PolicyAttributor()
        self.lens_explainer = lens_explainer or LensExplainer()
        self.governance_tuner = governance_tuner or GovernanceTuner()
        self.langfuse_adapter = langfuse_adapter

        self._evidence_cache: Dict[str, StructuredEvidence] = {}
        self._profile_cache: Dict[str, IntentEvidenceProfile] = {}

    async def register_run(self, correlation_ids: CorrelationIds) -> None:
        """Register a run and persist the run index when a store is available."""
        if self.store:
            try:
                await self.store.save_run_index(
                    correlation_ids=correlation_ids,
                    status="pending",
                )
                logger.debug(
                    f"EGBOrchestrator: Saved/updated run {correlation_ids.run_id} to store"
                )
            except Exception as e:
                logger.warning(f"EGBOrchestrator: Failed to save run index: {e}")

        link_result = await self.trace_linker.register_run(correlation_ids)
        if not link_result.success:
            logger.error(
                f"EGBOrchestrator: Failed to register run: {link_result.error}"
            )
            raise RuntimeError(f"Failed to register run: {link_result.error}")

    async def process_run(
        self,
        correlation_ids: CorrelationIds,
        trace_graph: TraceGraph,
        current_settings: Optional[GovernanceSettings] = None,
    ) -> EGBProcessResult:
        """Process one execution through trace, evidence, drift, and tuning."""
        result = EGBProcessResult(correlation_ids=correlation_ids)

        try:
            if self.store:
                try:
                    await self.store.save_run_index(
                        correlation_ids=correlation_ids,
                        status="pending",
                    )
                    logger.debug(
                        f"EGBOrchestrator: Saved/updated run {correlation_ids.run_id} to store in process_run"
                    )
                except Exception as e:
                    logger.warning(
                        f"EGBOrchestrator: Failed to save run index in process_run: {e}"
                    )

            link_result = await self.trace_linker.register_run(correlation_ids)
            if not link_result.success:
                result.errors.append(f"TraceLinker failed: {link_result.error}")

            _external_jobs = [
                node
                for node in trace_graph.nodes
                if hasattr(node, "node_type") and node.node_type.value == "external_job"
            ]

            evidence = await self.evidence_reducer.reduce_trace(
                trace=trace_graph,
                correlation_ids=correlation_ids,
            )
            result.structured_evidence = evidence
            self._evidence_cache[correlation_ids.run_id] = evidence

            await apply_process_drift_and_prescription(
                self,
                result,
                correlation_ids,
                evidence,
                current_settings,
            )
            await self._update_evidence_profile(correlation_ids, evidence)

            logger.info(
                f"EGBOrchestrator: Processed run {correlation_ids.run_id} "
                f"for intent {correlation_ids.intent_id}"
            )

        except Exception as e:
            logger.error(f"EGBOrchestrator: Failed to process run: {e}")
            result.errors.append(str(e))

        return result

    async def get_intent_profile(
        self,
        intent_id: str,
        workspace_id: str,
    ) -> Optional[IntentEvidenceProfile]:
        """Get or create the in-memory evidence profile for an intent."""
        cache_key = f"{workspace_id}:{intent_id}"
        profile = self._profile_cache.get(cache_key)

        if not profile:
            profile = IntentEvidenceProfile(
                intent_id=intent_id,
                workspace_id=workspace_id,
            )
            self._profile_cache[cache_key] = profile

        return profile

    async def get_drift_score_for_intent(
        self,
        intent_id: str,
        workspace_id: str,
    ) -> float:
        """Return the latest drift score for an intent, or 0.0 when absent."""
        if not self.store:
            return 0.0
        try:
            report = await self.store.get_latest_drift_report_by_intent(intent_id)
            if report:
                return report.overall_drift_score
        except Exception as e:
            logger.warning(
                f"EGBOrchestrator: Failed to get drift score for intent {intent_id}: {e}"
            )
        return 0.0

    async def get_drift_report(
        self,
        run_id: str,
        baseline_run_id: Optional[str] = None,
    ) -> Optional[RunDriftReport]:
        """Get a drift report for a run through the private drift seam."""
        return await get_drift_report_for_run(self, run_id, baseline_run_id)

    async def _rebuild_evidence(
        self, run_id: str, correlation_ids: CorrelationIds
    ) -> Optional[StructuredEvidence]:
        """Rebuild evidence through the private process seam."""
        return await rebuild_evidence(self, run_id, correlation_ids)

    async def explain_drift(
        self,
        run_id: str,
        user_context: Optional[str] = None,
    ) -> Optional[str]:
        """Request an LLM explanation for a drift report."""
        drift_report = await self.get_drift_report(run_id)
        if not drift_report:
            return None

        result = await self.lens_explainer.explain_drift(
            drift_report=drift_report,
            attribution=drift_report.drift_explanations,
            user_context=user_context,
        )

        drift_report.llm_explanation = result.explanation
        drift_report.needs_llm_explanation = False

        return result.explanation

    async def _update_evidence_profile(
        self,
        correlation_ids: CorrelationIds,
        evidence: StructuredEvidence,
    ) -> None:
        """
        Update the in-memory intent evidence profile.

        Existing behavior is preserved, including the current trace_graph lookup
        inside this method. A semantic fix for that behavior needs a separate
        bugfix plan.
        """
        cache_key = f"{correlation_ids.workspace_id}:{correlation_ids.intent_id}"

        profile = self._profile_cache.get(cache_key)
        if not profile:
            profile = IntentEvidenceProfile(
                intent_id=correlation_ids.intent_id,
                workspace_id=correlation_ids.workspace_id,
            )
            self._profile_cache[cache_key] = profile

        is_success = False
        if self.store:
            run_index = await self.store.get_run_index(correlation_ids.run_id)
            if run_index:
                is_success = run_index.is_success
            else:
                is_success = evidence.metrics.error_count == 0
        else:
            is_success = evidence.metrics.error_count == 0

        profile.total_runs += 1
        if is_success:
            profile.successful_runs += 1
        else:
            profile.failed_runs += 1

        now = _utc_now()
        if profile.first_run_at is None:
            profile.first_run_at = now
        profile.last_run_at = now

        profile.total_tokens += evidence.metrics.total_tokens
        profile.total_cost_usd += evidence.metrics.total_cost_usd

        if profile.total_runs > 0:
            profile.avg_latency_ms = (
                profile.avg_latency_ms * (profile.total_runs - 1)
                + evidence.metrics.total_latency_ms
            ) / profile.total_runs

        from backend.app.core.trace.trace_schema import TraceNodeType

        external_jobs = [
            node
            for node in trace_graph.nodes
            if hasattr(node, "node_type")
            and node.node_type == TraceNodeType.EXTERNAL_JOB
        ]

        gate_result = None
        outcome_result = determine_run_outcome(
            trace_graph=trace_graph,
            strictness_level=correlation_ids.strictness_level,
            gate_result=gate_result,
            error_count=evidence.metrics.error_count,
            external_jobs=external_jobs,
        )

        if self.store:
            await self.store.update_run_status(
                run_id=correlation_ids.run_id,
                outcome=outcome_result.outcome.value,
                gate_passed=outcome_result.gate_passed,
                error_count=outcome_result.error_count,
            )

        _drift_score = 0.0
        if outcome_result.outcome == RunOutcome.SUCCESS:
            profile.update_stability_score()
        elif outcome_result.outcome == RunOutcome.PARTIAL:
            profile.stability_score = profile.stability_score * 0.7
        else:
            profile.stability_score = max(0.0, profile.stability_score - 0.1)

        profile.updated_at = now
