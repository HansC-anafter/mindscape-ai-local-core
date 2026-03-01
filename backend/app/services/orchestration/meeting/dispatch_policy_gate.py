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
    binding_store=None,
) -> None:
    """Run policy checks on action items before dispatch.

    Mutates items in-place: sets landing_status='policy_blocked',
    landing_error, and policy_reason_code on failing items.

    Tool allowlist is resolved per-item using target_workspace_id
    (falls back to session workspace_id). Allowlists are cached
    per-workspace to avoid redundant store queries.

    Args:
        action_items: Items to validate (mutated in-place).
        workspace_id: Session (fallback) workspace ID.
        available_playbooks_cache: Formatted playbook list from engine preload.
        binding_store: Optional workspace resource binding store for tool allowlist.
    """
    # Build set of known playbook codes from the cache string
    known_playbook_codes = _parse_playbook_codes(available_playbooks_cache)

    # Per-workspace allowlist cache (lazy-loaded)
    _allowlist_cache: Dict[str, Optional[set]] = {}

    def _get_allowlist(ws_id: str) -> Optional[set]:
        if ws_id not in _allowlist_cache:
            _allowlist_cache[ws_id] = _load_tool_allowlist(ws_id, binding_store)
        return _allowlist_cache[ws_id]

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

        # Check 2: Tool allowlist (per target workspace)
        if tool_name and binding_store is not None:
            target_ws = item.get("target_workspace_id") or workspace_id
            allowed_tools = _get_allowlist(target_ws)
            if allowed_tools is not None and tool_name not in allowed_tools:
                _mark_blocked(
                    item,
                    reason_code="TOOL_NOT_ALLOWED",
                    message=f"Tool '{tool_name}' not in workspace '{target_ws}' allowlist",
                )
                continue


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


def _load_tool_allowlist(
    workspace_id: str,
    binding_store=None,
) -> Optional[set]:
    """Load allowed tool names from workspace resource bindings.

    Returns:
        Set of allowed tool names, or None if no binding_store
        (which means tool allowlist is not enforced).
    """
    if binding_store is None:
        return None
    try:
        from backend.app.models.workspace_resource_binding import ResourceType

        bindings = binding_store.list_bindings_by_workspace(
            workspace_id, resource_type=ResourceType.TOOL
        )
        if not bindings:
            return None  # fail-open: no TOOL bindings = no restriction
        return {b.resource_id for b in bindings}
    except Exception as exc:
        logger.warning("Failed to load tool allowlist for %s: %s", workspace_id, exc)
        return None
