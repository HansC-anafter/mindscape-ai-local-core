"""Proposed action helpers for policy checks."""

from typing import Any, Dict


def build_proposed_action(
    *,
    tool_id: str,
    tool_call_params: Dict[str, Any],
    risk_class: str,
) -> Dict[str, Any]:
    """Build a proposed action for user confirmation."""
    return {
        "tool_id": tool_id,
        "params": tool_call_params,
        "risk_class": risk_class,
        "requires_confirmation": True,
    }
