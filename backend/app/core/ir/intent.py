"""
Intent IR Schema

Intermediate representation for intent analysis results.
Extends ToolSlotAnalysisResult with additional metadata for staged model switching.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ToolRelevanceResult:
    """Tool relevance analysis result"""
    tool_slot: str
    relevance_score: float  # 0.0-1.0
    reasoning: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0


@dataclass
class ToolSlotAnalysisResult:
    """
    Tool slot analysis result (existing, kept for backward compatibility)

    This is the tool slot version of intent analysis (ToolCandidateSelection stage).
    Note: This is different from the global IntentAnalysisResult (IntentRouting stage).
    """
    relevant_tools: List[ToolRelevanceResult]  # 1-3 most relevant tools
    overall_reasoning: Optional[str] = None
    needs_confirmation: bool = False  # Whether user confirmation is needed when multiple tools are suitable
    confidence: float = 0.0  # Overall confidence (0.0-1.0)
    escalation_required: bool = False  # Whether strong precision stage is required
    reasons: Optional[List[str]] = None  # Escalation reasons


@dataclass
class IntentIR:
    """
    Intent IR Schema

    Structured intermediate representation for intent analysis results.
    Extends ToolSlotAnalysisResult with stage metadata and versioning.

    This IR is used to pass intent analysis results between stages:
    - ToolCandidateSelection stage → Plan generation stage
    - ToolCandidateSelection stage → Tool execution stage
    """
    # Core intent analysis result
    analysis_result: ToolSlotAnalysisResult

    # Stage metadata
    stage: str = "tool_candidate_selection"  # Stage name
    risk_level: str = "read"  # Risk level: "read", "write", "publish"

    # Model selection metadata
    model_used: Optional[str] = None  # Model name used for analysis
    profile_used: Optional[str] = None  # Capability profile used
    two_phase: bool = False  # Whether two-phase analysis was used
    recall_phase_result: Optional[ToolSlotAnalysisResult] = None  # Phase 2A result
    precision_phase_result: Optional[ToolSlotAnalysisResult] = None  # Phase 2B result

    # Timestamp
    timestamp: Optional[datetime] = None

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "version": self.version,
            "stage": self.stage,
            "risk_level": self.risk_level,
            "two_phase": self.two_phase,
            "analysis_result": {
                "relevant_tools": [
                    {
                        "tool_slot": tool.tool_slot,
                        "relevance_score": tool.relevance_score,
                        "reasoning": tool.reasoning,
                        "confidence": tool.confidence,
                    }
                    for tool in self.analysis_result.relevant_tools
                ],
                "overall_reasoning": self.analysis_result.overall_reasoning,
                "needs_confirmation": self.analysis_result.needs_confirmation,
                "confidence": self.analysis_result.confidence,
                "escalation_required": self.analysis_result.escalation_required,
                "reasons": self.analysis_result.reasons,
            },
        }

        if self.model_used:
            result["model_used"] = self.model_used
        if self.profile_used:
            result["profile_used"] = self.profile_used
        if self.recall_phase_result:
            result["recall_phase_result"] = self._result_to_dict(self.recall_phase_result)
        if self.precision_phase_result:
            result["precision_phase_result"] = self._result_to_dict(self.precision_phase_result)
        if self.timestamp:
            result["timestamp"] = self.timestamp.isoformat()
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @staticmethod
    def _result_to_dict(result: ToolSlotAnalysisResult) -> Dict[str, Any]:
        """Helper to convert ToolSlotAnalysisResult to dict"""
        return {
            "relevant_tools": [
                {
                    "tool_slot": tool.tool_slot,
                    "relevance_score": tool.relevance_score,
                    "reasoning": tool.reasoning,
                    "confidence": tool.confidence,
                }
                for tool in result.relevant_tools
            ],
            "overall_reasoning": result.overall_reasoning,
            "needs_confirmation": result.needs_confirmation,
            "confidence": result.confidence,
            "escalation_required": result.escalation_required,
            "reasons": result.reasons,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentIR":
        """Create IntentIR from dictionary"""
        analysis_result_data = data.get("analysis_result", {})
        analysis_result = ToolSlotAnalysisResult(
            relevant_tools=[
                ToolRelevanceResult(
                    tool_slot=tool["tool_slot"],
                    relevance_score=tool["relevance_score"],
                    reasoning=tool.get("reasoning"),
                    confidence=tool.get("confidence", 0.0),
                )
                for tool in analysis_result_data.get("relevant_tools", [])
            ],
            overall_reasoning=analysis_result_data.get("overall_reasoning"),
            needs_confirmation=analysis_result_data.get("needs_confirmation", False),
            confidence=analysis_result_data.get("confidence", 0.0),
            escalation_required=analysis_result_data.get("escalation_required", False),
            reasons=analysis_result_data.get("reasons"),
        )

        timestamp = None
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"])

        recall_result = None
        if data.get("recall_phase_result"):
            recall_result = cls._dict_to_result(data["recall_phase_result"])

        precision_result = None
        if data.get("precision_phase_result"):
            precision_result = cls._dict_to_result(data["precision_phase_result"])

        return cls(
            analysis_result=analysis_result,
            stage=data.get("stage", "tool_candidate_selection"),
            risk_level=data.get("risk_level", "read"),
            model_used=data.get("model_used"),
            profile_used=data.get("profile_used"),
            two_phase=data.get("two_phase", False),
            recall_phase_result=recall_result,
            precision_phase_result=precision_result,
            timestamp=timestamp,
            version=data.get("version", "1.0"),
            metadata=data.get("metadata"),
        )

    @staticmethod
    def _dict_to_result(data: Dict[str, Any]) -> ToolSlotAnalysisResult:
        """Helper to convert dict to ToolSlotAnalysisResult"""
        return ToolSlotAnalysisResult(
            relevant_tools=[
                ToolRelevanceResult(
                    tool_slot=tool["tool_slot"],
                    relevance_score=tool["relevance_score"],
                    reasoning=tool.get("reasoning"),
                    confidence=tool.get("confidence", 0.0),
                )
                for tool in data.get("relevant_tools", [])
            ],
            overall_reasoning=data.get("overall_reasoning"),
            needs_confirmation=data.get("needs_confirmation", False),
            confidence=data.get("confidence", 0.0),
            escalation_required=data.get("escalation_required", False),
            reasons=data.get("reasons"),
        )





