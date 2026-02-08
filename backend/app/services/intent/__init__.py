"""
Intent Analysis Package

Re-exports from the original intent_analyzer.py for backwards compatibility.
The individual modules (models.py, rule_matcher.py, coordinator.py) are prepared
for gradual migration but the main pipeline remains in intent_analyzer.py.
"""

# Re-export from original location for backwards compatibility
from backend.app.services.intent_analyzer import (
    InteractionType,
    TaskDomain,
    IntentAnalysisResult,
    RuleBasedIntentMatcher,
    LLMBasedIntentMatcher,
    PlaybookSelector,
    IntentDecisionCoordinator,
    IntentPipeline,
    _parse_json_from_response,
)

# Backwards-compatible alias
IntentAnalyzer = IntentPipeline

__all__ = [
    "InteractionType",
    "TaskDomain",
    "IntentAnalysisResult",
    "RuleBasedIntentMatcher",
    "LLMBasedIntentMatcher",
    "PlaybookSelector",
    "IntentDecisionCoordinator",
    "IntentPipeline",
    "IntentAnalyzer",
    "_parse_json_from_response",
]
