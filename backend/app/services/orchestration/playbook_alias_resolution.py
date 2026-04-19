"""Shared helpers for recovering playbook identity from tool-like outputs."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


def load_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
    """Load structured playbook spec from playbook.json if available."""
    try:
        from backend.app.services.playbook_loaders import PlaybookJsonLoader

        playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
        if playbook_json is None:
            return None
        if hasattr(playbook_json, "model_dump"):
            return playbook_json.model_dump(exclude_none=True)
    except Exception:
        return None
    return None


def parse_playbook_codes(cache_str: str) -> Set[str]:
    """Extract playbook codes from formatted cache lines.

    Cache format is typically ``- playbook_code: Playbook Name``.
    """
    codes: Set[str] = set()
    if not cache_str:
        return codes
    for raw_line in cache_str.strip().splitlines():
        line = raw_line.strip()
        if line.startswith("- ") and ":" in line:
            playbook_code = line[2:].split(":", 1)[0].strip()
            if playbook_code:
                codes.add(playbook_code)
    return codes


@lru_cache(maxsize=1)
def discover_local_playbook_codes() -> Set[str]:
    """Best-effort discovery of locally installed playbook codes."""
    service_dir = Path(__file__).resolve()
    app_dir = service_dir.parents[2]  # .../backend/app
    backend_dir = app_dir.parent

    codes: Set[str] = set()

    core_specs_dir = backend_dir / "playbooks" / "specs"
    if core_specs_dir.exists():
        for spec_path in core_specs_dir.glob("*.json"):
            if spec_path.stem:
                codes.add(spec_path.stem)

    i18n_specs_dir = backend_dir / "i18n" / "playbooks"
    if i18n_specs_dir.exists():
        for spec_path in i18n_specs_dir.glob("*/*.json"):
            if spec_path.stem:
                codes.add(spec_path.stem)

    capability_roots = [
        app_dir / "capabilities",
        Path("data") / "capabilities",
    ]
    for capability_root in capability_roots:
        if not capability_root.exists():
            continue
        for spec_path in capability_root.glob("*/playbooks/specs/*.json"):
            if spec_path.stem:
                codes.add(spec_path.stem)

    return codes


def extract_tool_slots(playbook_spec: Optional[Dict[str, Any]]) -> List[str]:
    """Return tool_slot declarations from a structured playbook spec."""
    if not isinstance(playbook_spec, dict):
        return []
    steps = playbook_spec.get("steps")
    if not isinstance(steps, list):
        return []

    slots: List[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        tool_slot = step.get("tool_slot")
        if isinstance(tool_slot, str) and tool_slot.strip():
            slots.append(tool_slot.strip())
    return slots


def _is_single_step_wrapper_playbook(
    playbook_spec: Optional[Dict[str, Any]],
    *,
    tool_name: str,
) -> bool:
    """Return True when the playbook is a thin wrapper around one tool slot."""
    if not isinstance(playbook_spec, dict):
        return False

    steps = playbook_spec.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        return False

    step = steps[0]
    if not isinstance(step, dict):
        return False

    tool_slot = step.get("tool_slot")
    if not isinstance(tool_slot, str) or not tool_slot.strip():
        return False

    slot = tool_slot.strip()
    suffix = tool_name.rsplit(".", 1)[-1]
    return slot == tool_name or slot.rsplit(".", 1)[-1] == suffix


def _match_tool_name_against_playbooks(
    tool_name: str,
    *,
    candidate_playbook_codes: Set[str],
    get_playbook_spec: Callable[[str], Optional[Dict[str, Any]]],
) -> Optional[str]:
    """Resolve a tool-like name against a candidate playbook set."""
    if not candidate_playbook_codes:
        return None

    exact_matches: List[str] = []
    suffix_matches: List[str] = []
    suffix = tool_name.rsplit(".", 1)[-1]

    for playbook_code in sorted(candidate_playbook_codes):
        playbook_spec = get_playbook_spec(playbook_code)
        if not _is_single_step_wrapper_playbook(playbook_spec, tool_name=tool_name):
            continue
        for tool_slot in extract_tool_slots(playbook_spec):
            if tool_slot == tool_name:
                exact_matches.append(playbook_code)
                break
            if tool_slot.rsplit(".", 1)[-1] == suffix:
                suffix_matches.append(playbook_code)
                break

    exact_matches = sorted(set(exact_matches))
    if len(exact_matches) == 1:
        return exact_matches[0]

    suffix_matches = sorted(set(suffix_matches))
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


def resolve_tool_name_playbook_alias(
    tool_name: Any,
    *,
    known_playbook_codes: Set[str],
    get_playbook_spec: Callable[[str], Optional[Dict[str, Any]]] = load_playbook_spec,
) -> Optional[str]:
    """Resolve a tool-like actuator name back to a unique playbook code."""
    if not isinstance(tool_name, str):
        return None
    name = tool_name.strip()
    if not name:
        return None
    if name in known_playbook_codes:
        return name

    # Persisted TaskIR / handoff replay can lose the meeting-time playbook cache.
    # If the tool name itself is a valid playbook code, recover it directly.
    if get_playbook_spec(name) is not None:
        return name

    resolved = _match_tool_name_against_playbooks(
        name,
        candidate_playbook_codes=known_playbook_codes,
        get_playbook_spec=get_playbook_spec,
    )
    if resolved:
        return resolved

    fallback_playbook_codes = discover_local_playbook_codes()
    if name in fallback_playbook_codes:
        return name

    return _match_tool_name_against_playbooks(
        name,
        candidate_playbook_codes=fallback_playbook_codes,
        get_playbook_spec=get_playbook_spec,
    )
