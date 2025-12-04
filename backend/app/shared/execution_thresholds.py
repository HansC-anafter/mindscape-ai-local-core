"""
Execution Thresholds Configuration

Centralized configuration for execution mode confidence thresholds.
All confidence threshold logic should read from this file.

IMPORTANT: Do NOT hardcode threshold values (0.6, 0.8, 0.9) anywhere else.

See: docs-internal/architecture/workspace-llm-agent-execution-mode.md
"""

from typing import Dict


# Execution priority -> confidence threshold mapping
EXECUTION_THRESHOLDS: Dict[str, float] = {
    "low": 0.9,      # Conservative: very high confidence required
    "medium": 0.8,   # Default threshold
    "high": 0.6      # Aggressive: lower threshold for auto-execution
}


def get_threshold(execution_priority: str) -> float:
    """
    Get confidence threshold for given execution priority

    Args:
        execution_priority: "low" | "medium" | "high"

    Returns:
        Confidence threshold (0.0-1.0)
    """
    return EXECUTION_THRESHOLDS.get(execution_priority, 0.8)


def should_auto_execute_readonly(
    execution_priority: str,
    confidence: float
) -> bool:
    """
    Determine if a readonly task should auto-execute

    For HIGH priority, all readonly tasks auto-execute regardless of confidence.
    For LOW/MEDIUM, check against threshold.

    Args:
        execution_priority: Execution priority level
        confidence: Confidence score from LLM analysis (0.0-1.0)

    Returns:
        True if task should auto-execute
    """
    if execution_priority == "high":
        return True
    threshold = get_threshold(execution_priority)
    return confidence >= threshold

