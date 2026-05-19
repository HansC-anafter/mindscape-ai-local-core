"""Dispatch policy gate mode resolution."""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

AUTO_GATE_MODE = "auto"
VALID_GATE_MODES = {"auto", "warn", "block"}


def _normalize_gate_mode(mode: Optional[str]) -> str:
    """Normalize gate mode, falling back to progressive auto mode."""
    normalized = (mode or AUTO_GATE_MODE).strip().lower()
    if normalized in VALID_GATE_MODES:
        return normalized
    logger.warning("Unknown contract_gate_mode '%s', falling back to auto", mode)
    return AUTO_GATE_MODE


def _resolve_effective_gate_mode(
    *,
    requested_mode: str,
    manifest_entry: Optional[Dict[str, Any]],
    playbook_spec: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    """Resolve the per-playbook effective gate mode."""
    if requested_mode == "block":
        return "block", "forced_block"
    if requested_mode == "warn":
        return "warn", "forced_warn"

    manifest_mode = _resolve_manifest_gate_override(manifest_entry)
    if manifest_mode == "block":
        return "block", "manifest_opt_in"
    if manifest_mode == "warn":
        return "warn", "manifest_override"
    if playbook_spec:
        return "block", "structured_playbook_spec"
    return "warn", "legacy_manifest"


def _resolve_manifest_gate_override(
    manifest_entry: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Read explicit contract gate opt-ins from manifest metadata if present."""
    if not isinstance(manifest_entry, dict):
        return None

    def _nested_get(data: Dict[str, Any], *path: str) -> Any:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    mode_candidates = (
        ("contract_gate_mode",),
        ("policy", "contract_gate_mode"),
        ("dispatch_policy", "contract_gate_mode"),
        ("governance", "contract_gate_mode"),
    )
    for path in mode_candidates:
        value = _nested_get(manifest_entry, *path)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"warn", "block"}:
                return normalized

    opt_in_candidates = (
        ("contract_gate_opt_in",),
        ("policy", "contract_gate_opt_in"),
        ("dispatch_policy", "contract_gate_opt_in"),
        ("governance", "contract_gate_opt_in"),
    )
    for path in opt_in_candidates:
        if _nested_get(manifest_entry, *path) is True:
            return "block"

    return None
