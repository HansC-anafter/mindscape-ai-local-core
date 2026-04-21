"""Declarative input-default resolvers for orchestration surfaces."""

from __future__ import annotations

import re
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency guard
    yaml = None

from backend.app.services.orchestration.playbook_alias_resolution import (
    load_playbook_spec,
)


def _has_material_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _clean_string_list(values: Any) -> List[str]:
    cleaned: List[str] = []
    if not isinstance(values, list):
        return cleaned
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _meeting_topic_materials(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    item = context.get("item") if isinstance(context.get("item"), dict) else {}
    payload = {
        "deliverable_id": context.get("deliverable_id"),
        "deliverable_name": context.get("deliverable_name"),
        "source_message": context.get("source_message"),
        "goals": list(context.get("goals") or []),
        "agenda": list(context.get("agenda") or []),
        "success_criteria": list(context.get("success_criteria") or []),
        "reference_notes": item.get("description"),
        "lens_id": context.get("lens_id"),
    }
    normalized = {
        key: deepcopy(value)
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }
    return normalized or None


def _meeting_source_content(context: Dict[str, Any]) -> Optional[str]:
    item = context.get("item") if isinstance(context.get("item"), dict) else {}
    source_lines: List[str] = []
    deliverable_name = str(context.get("deliverable_name") or "").strip()
    source_message = str(context.get("source_message") or "").strip()
    goals = [str(goal) for goal in context.get("goals") or [] if str(goal).strip()]
    agenda = [str(step) for step in context.get("agenda") or [] if str(step).strip()]
    description = str(item.get("description") or "").strip()
    if deliverable_name:
        source_lines.append(f"Deliverable: {deliverable_name}")
    if source_message:
        source_lines.append(f"Request: {source_message}")
    if goals:
        source_lines.append("Goals: " + "; ".join(goals))
    if agenda:
        source_lines.append("Agenda: " + "; ".join(agenda))
    if description:
        source_lines.append(f"Execution brief: {description}")
    return "\n".join(source_lines) if source_lines else None


def _planner_research_query(context: Dict[str, Any]) -> Optional[str]:
    value = context.get("research_query")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _planner_research_max_results(context: Dict[str, Any]) -> Optional[int]:
    value = context.get("research_max_results")
    if isinstance(value, int) and value > 0:
        return value
    return None


def _planner_phase_workspace_id(context: Dict[str, Any]) -> Optional[str]:
    value = context.get("workspace_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _planner_phase_ig_target_format(context: Dict[str, Any]) -> Optional[str]:
    phase_text = str(context.get("phase_text") or "")
    if re.search(r"\b(ig|instagram|caption|post|posts)\b|貼文", phase_text.lower()):
        return "ig_caption"
    return None


_RESOLVERS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "meeting.topic_materials": _meeting_topic_materials,
    "meeting.source_content": _meeting_source_content,
    "planner.research.query": _planner_research_query,
    "planner.research.max_results": _planner_research_max_results,
    "planner.phase.workspace_id": _planner_phase_workspace_id,
    "planner.phase.ig_target_format": _planner_phase_ig_target_format,
}


def apply_declarative_input_defaults(
    *,
    params: Dict[str, Any],
    rules: List[Dict[str, Any]],
    resolver_context: Dict[str, Any],
) -> bool:
    """Fill missing params from declarative rules."""
    changed = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        input_name = str(
            rule.get("input_name") or rule.get("param") or rule.get("name") or ""
        ).strip()
        if not input_name or _has_material_value(params.get(input_name)):
            continue

        value = None
        if "value" in rule:
            candidate = rule.get("value")
            if _has_material_value(candidate):
                value = deepcopy(candidate)
        else:
            resolver_name = str(rule.get("resolver") or "").strip()
            resolver = _RESOLVERS.get(resolver_name)
            if resolver is None:
                continue
            candidate = resolver(resolver_context)
            if _has_material_value(candidate):
                value = deepcopy(candidate)

        if _has_material_value(value):
            params[input_name] = value
            changed = True
    return changed


def load_playbook_meeting_input_defaults(playbook_code: str) -> List[Dict[str, Any]]:
    return _load_playbook_default_rules(playbook_code, field_name="meeting_input_defaults")


def load_playbook_planner_input_defaults(playbook_code: str) -> List[Dict[str, Any]]:
    return _load_playbook_default_rules(playbook_code, field_name="planner_input_defaults")


def _load_playbook_default_rules(playbook_code: str, *, field_name: str) -> List[Dict[str, Any]]:
    if not isinstance(playbook_code, str) or not playbook_code.strip():
        return []
    playbook_spec = load_playbook_spec(playbook_code.strip())
    if not isinstance(playbook_spec, dict):
        return []
    rules = playbook_spec.get(field_name)
    if not isinstance(rules, list):
        return []
    return [dict(rule) for rule in rules if isinstance(rule, dict)]


def load_tool_planner_input_defaults(tool_name: str) -> List[Dict[str, Any]]:
    if not isinstance(tool_name, str) or not tool_name.strip():
        return []
    return [dict(rule) for rule in _build_tool_planner_defaults_cache().get(tool_name.strip(), [])]


@lru_cache(maxsize=1)
def _build_tool_planner_defaults_cache() -> Dict[str, List[Dict[str, Any]]]:
    cache: Dict[str, List[Dict[str, Any]]] = {}
    if yaml is None:
        return cache

    capabilities_roots = [
        Path("/app/backend/app/capabilities"),
        Path(__file__).resolve().parents[2] / "capabilities",
    ]
    for capabilities_dir in capabilities_roots:
        if not capabilities_dir.is_dir():
            continue
        for capability_dir in capabilities_dir.iterdir():
            if not capability_dir.is_dir() or capability_dir.name.startswith(("_", ".")):
                continue
            manifest_path = capability_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
            try:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    manifest = yaml.safe_load(handle) or {}
            except Exception:
                continue

            capability_code = str(manifest.get("code") or capability_dir.name).strip()
            if not capability_code:
                continue

            for tool in manifest.get("tools", []) or []:
                if not isinstance(tool, dict):
                    continue
                tool_code = str(tool.get("name") or tool.get("code") or "").strip()
                if not tool_code:
                    continue
                rules = tool.get("planner_input_defaults")
                if not isinstance(rules, list):
                    continue
                normalized_rules = [dict(rule) for rule in rules if isinstance(rule, dict)]
                if not normalized_rules:
                    continue
                cache[f"{capability_code}.{tool_code}"] = normalized_rules
    return cache
