"""Explain why governance context sources were selected."""

from __future__ import annotations

from typing import Any, Mapping


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _included_sources(sources: Mapping[str, Any]) -> list[str]:
    included: list[str] = []
    if sources.get("canonical_item_count"):
        included.append("canonical_memory")
    if sources.get("personal_knowledge_count"):
        included.append("personal_knowledge")
    if sources.get("goal_count"):
        included.append("goal_ledger")
    if sources.get("has_project_memory"):
        included.append("project_memory")
    if sources.get("has_member_memory"):
        included.append("member_memory")
    if sources.get("has_spatial_schedule"):
        included.append("spatial_schedule")
    return included


def build_context_selection_explanation(
    *,
    governance_context: Mapping[str, Any],
    memory_packet: Mapping[str, Any],
) -> dict[str, Any]:
    sources = _as_mapping(governance_context.get("sources"))
    selection = _as_mapping(memory_packet.get("selection"))
    layers = _as_mapping(memory_packet.get("layers"))
    route = []
    for name, value in layers.items():
        if value not in (None, {}, []):
            route.append(str(name))
    included = _included_sources(sources)
    return {
        "source": "governance_context_read_model",
        "workspace_id": governance_context.get("workspace_id"),
        "profile_id": governance_context.get("profile_id"),
        "project_id": governance_context.get("project_id"),
        "workspace_mode": governance_context.get("mode"),
        "memory_scope": selection.get("memory_scope"),
        "included_sources": included,
        "route_layers": route,
        "reason": (
            "Selected context from workspace policy, memory scope, "
            "recent canonical memory, personal knowledge, goals, and object schedule evidence."
        ),
        "counts": {
            "canonical_items": int(sources.get("canonical_item_count") or 0),
            "personal_knowledge": int(sources.get("personal_knowledge_count") or 0),
            "goals": int(sources.get("goal_count") or 0),
        },
    }
