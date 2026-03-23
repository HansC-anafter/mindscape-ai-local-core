"""Pure planning helpers for DispatchOrchestrator."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set


def normalize_phase_inputs(
    *,
    phases: List[Any],
    action_items: List[Dict[str, Any]],
    session: Any,
) -> None:
    """Hydrate weakly-specified meeting phases into executable inputs."""
    phase_map: Dict[str, Any] = {p.id: p for p in phases}
    items_by_title: Dict[str, Dict[str, Any]] = {
        item.get("title", ""): item for item in action_items if item.get("title")
    }
    for phase in phases:
        params = dict(phase.input_params or {})
        changed = False

        if phase.tool_name == "frontier_research.process_papers_pipeline":
            query, max_results = derive_research_context(
                phase=phase,
                phase_map=phase_map,
                session=session,
            )
            if not params.get("query") and query:
                params["query"] = query
                changed = True
            if not params.get("max_results") and max_results:
                params["max_results"] = max_results
                changed = True
            if not params.get("sources"):
                params["sources"] = ["pubmed", "semantic_scholar"]
                changed = True

        playbook_code = extract_playbook_code(getattr(phase, "preferred_engine", None))
        if playbook_code == "article_draft":
            query, max_results = derive_research_context(
                phase=phase,
                phase_map=phase_map,
                session=session,
            )
            if not params.get("topic") and query:
                params["topic"] = query
                changed = True
            if not params.get("workspace_id"):
                workspace_id = phase.target_workspace_id or getattr(
                    session, "workspace_id", None
                )
                if workspace_id:
                    params["workspace_id"] = workspace_id
                    changed = True
            if not params.get("max_results") and max_results:
                params["max_results"] = max_results
                changed = True
            if not params.get("sources"):
                params["sources"] = ["pubmed", "semantic_scholar"]
                changed = True
            if not params.get("language"):
                params["language"] = "zh-TW"
                changed = True

            phase_text = " ".join(
                filter(None, [phase.name, getattr(phase, "description", "") or ""])
            )
            if not params.get("target_format") and looks_like_ig_work(phase_text):
                params["target_format"] = "ig_caption"
                changed = True

        if changed:
            phase.input_params = params
            item = items_by_title.get(phase.name)
            if item is not None:
                item["input_params"] = dict(params)


def derive_research_context(
    *,
    phase: Any,
    phase_map: Dict[str, Any],
    session: Any,
) -> tuple[Optional[str], Optional[int]]:
    """Infer a research query/max_results from upstream dependency hints."""
    queries: List[str] = []
    max_results: List[int] = []
    visited: Set[str] = set()

    def visit(phase_id: str) -> None:
        if phase_id in visited:
            return
        visited.add(phase_id)
        dep = phase_map.get(phase_id)
        if dep is None:
            return

        params = dep.input_params or {}
        query = params.get("query") or params.get("topic")
        if isinstance(query, str) and query.strip():
            queries.append(query.strip())

        limit = params.get("max_results")
        if isinstance(limit, int) and limit > 0:
            max_results.append(limit)

        for upstream_id in dep.depends_on or []:
            visit(upstream_id)

    for dep_id in phase.depends_on or []:
        visit(dep_id)

    if not queries:
        params = phase.input_params or {}
        query = params.get("query") or params.get("topic")
        if isinstance(query, str) and query.strip():
            queries.append(query.strip())

    if not queries:
        agenda = getattr(session, "agenda", None) or []
        if isinstance(agenda, list):
            for item in agenda:
                if isinstance(item, str) and item.strip():
                    queries.append(item.strip())
                    break

    query = queries[0] if queries else None
    derived_limit = sum(max_results) if max_results else None
    return query, derived_limit


def looks_like_ig_work(text: str) -> bool:
    """Detect caption/post-oriented phases and route them to IG mode."""
    return bool(
        re.search(
            r"\b(ig|instagram|caption|post|posts)\b|貼文",
            (text or "").lower(),
        )
    )


def extract_playbook_code(engine: Optional[str]) -> Optional[str]:
    """Extract playbook code from engine string (e.g. 'playbook:generic')."""
    if engine and engine.startswith("playbook:"):
        return engine.split(":", 1)[1]
    return None


def build_ir_provenance(
    *,
    phase: Any,
    action_item: Dict[str, Any],
    engine: str,
    session: Any,
) -> Dict[str, Any]:
    """Build a provenance snapshot without assuming optional PhaseIR fields exist."""
    dependencies = phase.depends_on or action_item.get("depends_on")
    if dependencies is None:
        dependencies = action_item.get("blocked_by") or []

    return {
        "preferred_engine": engine,
        "tool_name": getattr(phase, "tool_name", None),
        "rationale": getattr(phase, "rationale", None)
        or action_item.get("rationale"),
        "dependencies": list(dependencies or []),
        "meeting_session_id": getattr(session, "id", None),
        "phase_id": phase.id,
        "priority": getattr(phase, "priority", None) or action_item.get("priority"),
    }
