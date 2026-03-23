from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ToolRelevanceResult:
    """Tool relevance analysis result"""

    tool_slot: str
    relevance_score: float
    reasoning: Optional[str] = None
    confidence: float = 0.0


@dataclass
class ToolSlotAnalysisResult:
    """Tool slot analysis result"""

    relevant_tools: List[ToolRelevanceResult]
    overall_reasoning: Optional[str] = None
    needs_confirmation: bool = False
    confidence: float = 0.0
    escalation_required: bool = False
    reasons: Optional[List[str]] = None
