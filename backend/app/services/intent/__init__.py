"""
Intent Analysis Package

Provides a 3-layer intent analysis pipeline for determining user intent and selecting appropriate playbooks.

Modules:
- models: Core data structures (enums, IntentAnalysisResult)
- utils: JSON parsing utilities
- rule_matcher: Regex-based pattern matching
- llm_matcher: LLM-based semantic understanding
- playbook_selector: Playbook selection and context preparation
- coordinator: Coordinates rule-based and LLM-based matching

The main pipeline remains in intent_analyzer.py for backward compatibility.
"""

# Re-export all public interfaces for backward compatibility
from .models import (
    InteractionType,
    TaskDomain,
    IntentAnalysisResult,
)
from .utils import (
    parse_json_from_response,
    _parse_json_from_response,  # Legacy alias
)
from .rule_matcher import RuleBasedIntentMatcher
from .llm_matcher import LLMBasedIntentMatcher
from .playbook_selector import PlaybookSelector
from .coordinator import IntentDecisionCoordinator

# IntentPipeline is still in intent_analyzer.py for now
# This allows gradual migration without breaking existing imports

__all__ = [
    # Models
    "InteractionType",
    "TaskDomain",
    "IntentAnalysisResult",
    # Utilities
    "parse_json_from_response",
    "_parse_json_from_response",
    # Classes
    "RuleBasedIntentMatcher",
    "LLMBasedIntentMatcher",
    "PlaybookSelector",
    "IntentDecisionCoordinator",
]
