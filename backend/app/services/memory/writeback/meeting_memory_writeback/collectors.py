"""Phase-2 evidence collector registry helpers."""

from backend.app.services.memory.writeback.evidence_collectors import (
    EvidenceCollectorRegistry,
    ExecutionTraceEvidenceCollector,
    GovernanceDecisionEvidenceCollector,
    IntentLogEvidenceCollector,
    LensPatchEvidenceCollector,
    StageResultEvidenceCollector,
)


def build_phase2_collector_registry(
    *,
    evidence_link_store,
    meeting_session_store,
    stage_results_store,
    task_store,
    intent_log_store,
    governance_store,
    lens_patch_store,
    stage_result_collector=None,
    execution_trace_collector=None,
    intent_log_collector=None,
    governance_decision_collector=None,
    lens_patch_collector=None,
):
    """Build the phase-2 evidence collector registry with injected overrides."""
    return EvidenceCollectorRegistry(
        [
            stage_result_collector
            or StageResultEvidenceCollector(
                evidence_link_store=evidence_link_store,
                meeting_session_store=meeting_session_store,
                stage_results_store=stage_results_store,
            ),
            execution_trace_collector
            or ExecutionTraceEvidenceCollector(
                evidence_link_store=evidence_link_store,
                meeting_session_store=meeting_session_store,
                task_store=task_store,
            ),
            intent_log_collector
            or IntentLogEvidenceCollector(
                evidence_link_store=evidence_link_store,
                intent_log_store=intent_log_store,
            ),
            governance_decision_collector
            or GovernanceDecisionEvidenceCollector(
                evidence_link_store=evidence_link_store,
                meeting_session_store=meeting_session_store,
                governance_store=governance_store,
            ),
            lens_patch_collector
            or LensPatchEvidenceCollector(
                evidence_link_store=evidence_link_store,
                lens_patch_store=lens_patch_store,
            ),
        ]
    )
