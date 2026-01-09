"""
EGB Schemas

Core data models for Evidence-Backed Governance Bridge.
"""

from .correlation_ids import CorrelationIds
from .evidence_profile import (
    IntentEvidenceProfile,
    RunSummary,
    ToolPathSummary,
    PolicyIntervention,
    DriftLevel,
)
from .drift_report import (
    RunDriftReport,
    DriftScores,
    DriftExplanation,
    ImpactAssessment,
    EvidenceRef,
)
from .governance_prescription import (
    GovernancePrescription,
    TunerRecommendation,
    GovernanceAction,
    ExpectedOutcome,
    RiskAssessment,
    KnobType,
)
from .decision_record import DecisionRecord
from .structured_evidence import (
    StructuredEvidence,
    ToolPath,
    RetrievalEvidence,
    PolicyCheckEvidence,
    StrictnessChange,
    TraceMetrics,
)

__all__ = [
    # Correlation
    "CorrelationIds",

    # Evidence Profile
    "IntentEvidenceProfile",
    "RunSummary",
    "ToolPathSummary",
    "PolicyIntervention",
    "DriftLevel",

    # Drift Report
    "RunDriftReport",
    "DriftScores",
    "DriftExplanation",
    "ImpactAssessment",
    "EvidenceRef",

    # Governance Prescription
    "GovernancePrescription",
    "TunerRecommendation",
    "GovernanceAction",
    "ExpectedOutcome",
    "RiskAssessment",
    "KnobType",

    # Decision Record
    "DecisionRecord",

    # Structured Evidence
    "StructuredEvidence",
    "ToolPath",
    "RetrievalEvidence",
    "PolicyCheckEvidence",
    "StrictnessChange",
    "TraceMetrics",
]

