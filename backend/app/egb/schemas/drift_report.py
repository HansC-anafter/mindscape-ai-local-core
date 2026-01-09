"""
Run Drift Report Schema

Execution drift report - Drift points, causes, and impacts of this run relative to previous/baseline run.
This is one of EGB's core outputs, used to answer "What's different about this execution compared to the last? Why?"
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid

from .evidence_profile import DriftLevel


class DriftType(str, Enum):
    """Drift types"""
    EVIDENCE = "evidence"        # Evidence drift (retrieval chunks differences)
    PATH = "path"                # Path drift (tool call sequence differences)
    CONSTRAINT = "constraint"    # Constraint drift (policy/strictness changes)
    SEMANTIC = "semantic"        # Semantic drift (output claim differences)
    COST = "cost"                # Cost drift (token/time differences)
    EXTERNAL_JOB = "external_job"  # P0-8: External workflow drift


class AttributionType(str, Enum):
    """Attribution types"""
    POLICY = "policy"            # Caused by policy
    LENS = "lens"                # Caused by Mind-Lens
    DATA = "data"                # Data source change
    MODEL = "model"              # Model version change
    INPUT = "input"              # Input difference
    UNKNOWN = "unknown"          # Unknown cause


@dataclass
class EvidenceRef:
    """Evidence reference - Points to specific trace/span"""
    ref_type: str                # "trace" | "span" | "chunk"
    ref_id: str                  # trace_id, span_id, or chunk_id
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "description": self.description,
        }


@dataclass
class DriftExplanation:
    """
    Drift explanation - Human-readable description of drift cause

    This is the data source for frontend "drift breakdown card".
    """
    drift_type: DriftType
    explanation: str             # Human-readable explanation, e.g., "Retrieval source changed from internal files to external API"
    severity: str                # "low" | "medium" | "high"
    impact: str                  # Impact description

    # Attribution
    attribution_type: AttributionType
    attributed_to: Optional[str] = None  # Specific attribution target (policy_id, lens_id, etc.)

    # Evidence reference
    evidence_refs: List[EvidenceRef] = field(default_factory=list)

    # Suggested actions
    suggested_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_type": self.drift_type.value,
            "explanation": self.explanation,
            "severity": self.severity,
            "impact": self.impact,
            "attribution_type": self.attribution_type.value,
            "attributed_to": self.attributed_to,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "suggested_action": self.suggested_action,
        }


@dataclass
class ImpactAssessment:
    """Impact assessment"""
    output_affected: bool        # Whether output is affected
    quality_impact: str          # "none" | "minor" | "major" | "critical"
    cost_impact: str             # "none" | "increased" | "decreased"
    reliability_impact: str      # "none" | "improved" | "degraded"

    risk_level: str = "low"      # "low" | "medium" | "high"
    requires_attention: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_affected": self.output_affected,
            "quality_impact": self.quality_impact,
            "cost_impact": self.cost_impact,
            "reliability_impact": self.reliability_impact,
            "risk_level": self.risk_level,
            "requires_attention": self.requires_attention,
        }


@dataclass
class DriftScores:
    """
    Drift scores - Quantified drift values for each dimension

    This is the output of DriftScorer.
    """
    evidence_drift: float = 0.0      # 0.0-1.0
    path_drift: float = 0.0          # 0.0-1.0
    constraint_drift: float = 0.0    # 0.0-1.0
    semantic_drift: float = 0.0      # 0.0-1.0
    cost_drift: float = 0.0          # 0.0-1.0
    external_job_drift: float = 0.0  # P0-8: External workflow drift (0.0-1.0)

    # P0-4 hard rule: WEIGHTS must be ClassVar to avoid being treated as a field by dataclass
    from typing import ClassVar

    # Weight coefficients
    WEIGHTS: ClassVar[Dict[str, float]] = {
        "evidence": 0.18,        # Retrieval evidence
        "path": 0.22,           # Tool path
        "constraint": 0.13,      # Constraint changes
        "semantic": 0.27,        # Semantic changes (most important)
        "cost": 0.09,            # Cost changes
        "external_job": 0.11,   # P0-8: External workflow drift
    }

    @property
    def overall_score(self) -> float:
        """Calculate weighted total score"""
        return (
            self.evidence_drift * self.WEIGHTS["evidence"] +
            self.path_drift * self.WEIGHTS["path"] +
            self.constraint_drift * self.WEIGHTS["constraint"] +
            self.semantic_drift * self.WEIGHTS["semantic"] +
            self.cost_drift * self.WEIGHTS["cost"] +
            self.external_job_drift * self.WEIGHTS["external_job"]  # ⚠️ P0-8
        )

    @property
    def level(self) -> DriftLevel:
        """Return drift level based on total score"""
        return DriftLevel.from_score(self.overall_score)

    @property
    def dominant_drift(self) -> DriftType:
        """Return most significant drift type"""
        drifts = {
            DriftType.EVIDENCE: self.evidence_drift,
            DriftType.PATH: self.path_drift,
            DriftType.CONSTRAINT: self.constraint_drift,
            DriftType.SEMANTIC: self.semantic_drift,
            DriftType.COST: self.cost_drift,
            DriftType.EXTERNAL_JOB: self.external_job_drift,  # ⚠️ P0-8
        }
        return max(drifts, key=drifts.get)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_drift": self.evidence_drift,
            "path_drift": self.path_drift,
            "constraint_drift": self.constraint_drift,
            "semantic_drift": self.semantic_drift,
            "cost_drift": self.cost_drift,
            "external_job_drift": self.external_job_drift,  # ⚠️ P0-8
            "overall_score": self.overall_score,
            "level": self.level.value,
            "dominant_drift": self.dominant_drift.value,
        }


@dataclass
class RunDriftReport:
    """
    Execution drift report

    Drift analysis report of this run relative to previous/baseline run.
    Used to answer "What's different about this execution compared to the last? Where is it drifting? Why?"

    This is the data source for frontend "drift report" panel.
    """

    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str = ""
    baseline_run_id: Optional[str] = None  # Baseline run (previous or specified baseline)
    intent_id: str = ""
    workspace_id: str = ""

    # Drift scores
    drift_scores: DriftScores = field(default_factory=DriftScores)

    # Drift source breakdown (human-readable)
    drift_explanations: List[DriftExplanation] = field(default_factory=list)

    # Impact assessment
    impact_assessment: Optional[ImpactAssessment] = None

    # Evidence references (all related evidence)
    evidence_refs: List[EvidenceRef] = field(default_factory=list)

    # P0-5 addition: Semantic drift diff pointers (JSON Pointer list)
    semantic_diff_pointers: List[str] = field(default_factory=list)

    # Whether LLM explanation is needed
    needs_llm_explanation: bool = False
    llm_explanation: Optional[str] = None  # Explanation generated by LensExplainer

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def overall_drift_score(self) -> float:
        """Overall drift score"""
        return self.drift_scores.overall_score

    @property
    def drift_level(self) -> DriftLevel:
        """Drift level"""
        return self.drift_scores.level

    @property
    def is_stable(self) -> bool:
        """Whether stable"""
        return self.drift_level == DriftLevel.STABLE

    @property
    def requires_attention(self) -> bool:
        """Whether attention is needed"""
        if self.impact_assessment:
            return self.impact_assessment.requires_attention
        return self.drift_level in [DriftLevel.MODERATE, DriftLevel.HIGH]

    def get_top_drifts(self, n: int = 3) -> List[DriftExplanation]:
        """Get top N most significant drift explanations"""
        severity_order = {"high": 0, "medium": 1, "low": 2}
        sorted_explanations = sorted(
            self.drift_explanations,
            key=lambda x: severity_order.get(x.severity, 3)
        )
        return sorted_explanations[:n]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "report_id": self.report_id,
            "run_id": self.run_id,
            "baseline_run_id": self.baseline_run_id,
            "intent_id": self.intent_id,
            "workspace_id": self.workspace_id,
            "drift_scores": self.drift_scores.to_dict(),
            "overall_drift_score": self.overall_drift_score,
            "drift_level": self.drift_level.value,
            "is_stable": self.is_stable,
            "requires_attention": self.requires_attention,
            "drift_explanations": [e.to_dict() for e in self.drift_explanations],
            "impact_assessment": self.impact_assessment.to_dict() if self.impact_assessment else None,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "semantic_diff_pointers": self.semantic_diff_pointers,  # P0-5 addition
            "needs_llm_explanation": self.needs_llm_explanation,
            "llm_explanation": self.llm_explanation,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunDriftReport":
        """Deserialize from dictionary"""
        report = cls(
            report_id=data.get("report_id", str(uuid.uuid4())),
            run_id=data["run_id"],
            baseline_run_id=data.get("baseline_run_id"),
            intent_id=data["intent_id"],
            workspace_id=data.get("workspace_id", ""),
            needs_llm_explanation=data.get("needs_llm_explanation", False),
            llm_explanation=data.get("llm_explanation"),
        )

        # Parse drift scores
        if data.get("drift_scores"):
            scores_data = data["drift_scores"]
            report.drift_scores = DriftScores(
                evidence_drift=scores_data.get("evidence_drift", 0.0),
                path_drift=scores_data.get("path_drift", 0.0),
                constraint_drift=scores_data.get("constraint_drift", 0.0),
                semantic_drift=scores_data.get("semantic_drift", 0.0),
                cost_drift=scores_data.get("cost_drift", 0.0),
                external_job_drift=scores_data.get("external_job_drift", 0.0),  # ⚠️ P0-8
            )

        # Parse datetime
        if data.get("created_at"):
            report.created_at = datetime.fromisoformat(data["created_at"])

        return report

