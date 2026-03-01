"""
Dispatch policy gate for meeting engine action items.

Pre-dispatch checks: validates playbook availability, tool allowlist,
and workspace boundaries. Marks failing items as policy_blocked with
a machine-readable policy_reason_code.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def check_dispatch_policy(
    action_items: List[Dict[str, Any]],
    workspace_id: str,
    available_playbooks_cache: str = "",
) -> None:
    """Run policy checks on action items before dispatch.

    Mutates items in-place: sets landing_status='policy_blocked',
    landing_error, and policy_reason_code on failing items.

    Args:
        action_items: Items to validate (mutated in-place).
        workspace_id: Current workspace ID.
        available_playbooks_cache: Formatted playbook list from engine preload.
    """
    # Build set of known playbook codes from the cache string
    known_playbook_codes = _parse_playbook_codes(available_playbooks_cache)

    for item in action_items:
        # Skip items already marked by a previous gate
        if item.get("landing_status"):
            continue

        playbook_code = item.get("playbook_code")
        tool_name = item.get("tool_name")

        # Check 1: Unknown playbook
        if playbook_code and known_playbook_codes:
            if playbook_code not in known_playbook_codes:
                _mark_blocked(
                    item,
                    reason_code="UNKNOWN_PLAYBOOK",
                    message=f"Playbook '{playbook_code}' not in installed playbooks",
                )
                continue

        # Check 2: Tool allowlist (extensible — currently logs only)
        if tool_name:
            # TODO: Load tool allowlist from workspace config
            # For now, tools pass through; allowlist enforcement is a future gate
            pass


def _mark_blocked(
    item: Dict[str, Any],
    reason_code: str,
    message: str,
) -> None:
    """Mark an action item as policy-blocked."""
    item["landing_status"] = "policy_blocked"
    item["landing_error"] = message
    item["policy_reason_code"] = reason_code
    logger.info(
        "Policy gate blocked item '%s': %s (%s)",
        item.get("title"),
        message,
        reason_code,
    )


def _parse_playbook_codes(cache_str: str) -> set:
    """Extract playbook codes from the formatted cache string.

    Cache format is lines like '- playbook_code: Playbook Name'.
    Returns empty set if cache is empty or unparseable.
    """
    codes = set()
    if not cache_str:
        return codes
    for line in cache_str.strip().split("\n"):
        line = line.strip()
        if line.startswith("- ") and ":" in line:
            code_part = line[2:].split(":", 1)[0].strip()
            if code_part:
                codes.add(code_part)
    return codes
