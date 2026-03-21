"""Utilities for lightweight execution status responses."""

from typing import Any, Dict, Optional


STATUS_CTX_HEAVY_KEYS = (
    "result",
    "workflow_result",
    "step_outputs",
    "outputs",
    "conversation_state",
)


def trim_execution_context_for_status(
    execution_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a lightweight execution_context for /status responses."""
    if not isinstance(execution_context, dict):
        return {}
    return {
        key: value
        for key, value in execution_context.items()
        if key not in STATUS_CTX_HEAVY_KEYS
    }
