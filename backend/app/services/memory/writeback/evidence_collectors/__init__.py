"""Collector seams for secondary governed-memory evidence sources."""

from .base import EvidenceCollectionResult
from .collector_registry import EvidenceCollectorRegistry
from .execution_trace_collector import ExecutionTraceEvidenceCollector
from .governance_decision_collector import GovernanceDecisionEvidenceCollector
from .intent_log_collector import IntentLogEvidenceCollector
from .lens_patch_collector import LensPatchEvidenceCollector
from .stage_result_collector import StageResultEvidenceCollector

__all__ = [
    "EvidenceCollectionResult",
    "EvidenceCollectorRegistry",
    "ExecutionTraceEvidenceCollector",
    "GovernanceDecisionEvidenceCollector",
    "IntentLogEvidenceCollector",
    "LensPatchEvidenceCollector",
    "StageResultEvidenceCollector",
]
