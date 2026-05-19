"""Manifest and allowlist source helpers for dispatch policy gating."""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.services.orchestration.playbook_alias_resolution import (
    extract_tool_slots,
    load_playbook_spec,
    parse_playbook_codes,
    resolve_tool_name_playbook_alias,
)

logger = logging.getLogger(__name__)


def _load_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
    """Load structured playbook spec from playbook.json if available."""
    try:
        return load_playbook_spec(playbook_code)
    except Exception as exc:
        logger.debug("Failed to load playbook.json for %s: %s", playbook_code, exc)
        return None


def _parse_playbook_codes(cache_str: str) -> set:
    """Extract playbook codes from the formatted cache string."""
    return parse_playbook_codes(cache_str)


def _load_tool_allowlist(
    workspace_id: str,
    binding_store=None,
) -> Optional[set]:
    """Load allowed tool names from workspace resource bindings."""
    if binding_store is None:
        return None
    try:
        from backend.app.models.workspace_resource_binding import ResourceType

        bindings = binding_store.list_bindings_by_workspace(
            workspace_id, resource_type=ResourceType.TOOL
        )
        if not bindings:
            return None
        return {b.resource_id for b in bindings}
    except Exception as exc:
        logger.warning("Failed to load tool allowlist for %s: %s", workspace_id, exc)
        return None


def _build_manifest_cache(playbook_codes: Set[str]) -> Dict[str, Any]:
    """Build a minimal playbook manifest cache from affordance declarations."""
    try:
        from backend.app.services.manifest_utils import resolve_playbook_affordance

        manifest_cache: Dict[str, Any] = {}
        for playbook_code in playbook_codes:
            affordance = resolve_playbook_affordance(playbook_code)
            if affordance:
                manifest_cache[playbook_code] = affordance
        return manifest_cache
    except Exception as exc:
        logger.debug("Failed to build manifest cache for policy gate: %s", exc)
        return {}


def _get_consumes_types(
    playbook_code: str,
    manifest_cache: Dict[str, Any],
) -> Set[str]:
    """Extract required consumes types for a playbook from manifest cache."""
    pb_entry = manifest_cache.get(playbook_code)
    if not isinstance(pb_entry, dict):
        return set()
    consumes = pb_entry.get("consumes") or []
    return {
        (c.get("type", "") if isinstance(c, dict) else c)
        for c in consumes
        if c
    }


def _get_available_types(
    workspace_data_sources: Dict[str, Any],
) -> Set[str]:
    """Extract available asset types from workspace data_sources."""
    types: Set[str] = set()
    for _pack_id, pack_data in workspace_data_sources.items():
        if isinstance(pack_data, dict):
            for prod in pack_data.get("produces", []):
                if isinstance(prod, dict) and prod.get("type"):
                    types.add(prod["type"])
    return types


def _canonicalize_tool_name(
    tool_name: Any,
    allowed_tools: Set[str],
) -> Tuple[Optional[str], List[str]]:
    """Return canonical tool name from allowlist, if resolvable."""
    if not isinstance(tool_name, str):
        return None, []
    name = tool_name.strip()
    if not name:
        return None, []
    if name in allowed_tools:
        return name, []

    suffix = name.rsplit(".", 1)[-1]
    candidates = [
        allowed for allowed in allowed_tools if allowed.rsplit(".", 1)[-1] == suffix
    ]
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


def _resolve_tool_name_playbook_alias(
    tool_name: Any,
    *,
    known_playbook_codes: Set[str],
    get_playbook_spec,
) -> Optional[str]:
    """Resolve tool-like actuator names back to a unique playbook code."""
    return resolve_tool_name_playbook_alias(
        tool_name,
        known_playbook_codes=known_playbook_codes,
        get_playbook_spec=get_playbook_spec,
    )


def _extract_tool_slots(playbook_spec: Optional[Dict[str, Any]]) -> List[str]:
    return extract_tool_slots(playbook_spec)
