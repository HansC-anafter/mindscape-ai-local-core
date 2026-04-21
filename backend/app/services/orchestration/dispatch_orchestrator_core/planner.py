"""Pure planning helpers for DispatchOrchestrator."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from backend.app.services.orchestration.default_input_resolvers import (
    apply_declarative_input_defaults,
    load_playbook_planner_input_defaults,
    load_tool_planner_input_defaults,
)
from backend.app.services.orchestration.playbook_alias_resolution import (
    load_playbook_spec,
    parse_playbook_codes,
    resolve_tool_name_playbook_alias,
)
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.tools.workspace_tools_core import task_to_payload


WORKSPACE_PICK_TOOL_NAMES = {
    "workspace.pick_relevant_execution",
    "workspace_pick_relevant_execution",
}
EXECUTION_CANDIDATE_TASK_TYPES = {"playbook_execution", "tool_execution"}
EXECUTION_CANDIDATE_EXCLUDED_PACKS = {"meeting_projection"}
DEFAULT_EXECUTION_CANDIDATE_LIMIT = 20


def normalize_phase_inputs(
    *,
    phases: List[Any],
    action_items: List[Dict[str, Any]],
    session: Any,
    available_playbooks_cache: str = "",
    project_id: Optional[str] = None,
) -> None:
    """Hydrate weakly-specified meeting phases into executable inputs."""
    phase_map: Dict[str, Any] = {p.id: p for p in phases}
    items_by_title: Dict[str, Dict[str, Any]] = {
        item.get("title", ""): item for item in action_items if item.get("title")
    }
    known_playbook_codes = parse_playbook_codes(available_playbooks_cache)
    playbook_spec_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def get_playbook_spec(playbook_code: str) -> Optional[Dict[str, Any]]:
        if playbook_code not in playbook_spec_cache:
            playbook_spec_cache[playbook_code] = load_playbook_spec(playbook_code)
        return playbook_spec_cache[playbook_code]

    for phase in phases:
        params = dict(phase.input_params or {})
        changed = False
        item = items_by_title.get(phase.name)

        if phase.tool_name:
            rescued_playbook = resolve_tool_name_playbook_alias(
                phase.tool_name,
                known_playbook_codes=known_playbook_codes,
                get_playbook_spec=get_playbook_spec,
            )
            if rescued_playbook:
                original_tool_name = phase.tool_name
                phase.preferred_engine = f"playbook:{rescued_playbook}"
                phase.tool_name = None
                changed = True
                if item is not None:
                    item["tool_name_original"] = item.get("tool_name") or original_tool_name
                    item["tool_name"] = None
                    item["playbook_code"] = rescued_playbook
                    item["tool_name_rerouted_to_playbook"] = True
                    item["preferred_engine"] = phase.preferred_engine

        playbook_code = extract_playbook_code(getattr(phase, "preferred_engine", None))
        planner_rules: List[Dict[str, Any]] = []
        if phase.tool_name:
            planner_rules.extend(load_tool_planner_input_defaults(phase.tool_name))
        if playbook_code:
            planner_rules.extend(load_playbook_planner_input_defaults(playbook_code))
        if planner_rules:
            query, max_results = derive_research_context(
                phase=phase,
                phase_map=phase_map,
                session=session,
            )
            phase_text = " ".join(
                filter(None, [phase.name, getattr(phase, "description", "") or ""])
            )
            workspace_id = phase.target_workspace_id or getattr(session, "workspace_id", None)
            if apply_declarative_input_defaults(
                params=params,
                rules=planner_rules,
                resolver_context={
                    "phase": phase,
                    "session": session,
                    "workspace_id": workspace_id,
                    "phase_text": phase_text,
                    "research_query": query,
                    "research_max_results": max_results,
                },
            ):
                changed = True

        if phase.tool_name in WORKSPACE_PICK_TOOL_NAMES:
            if not params.get("user_query"):
                user_query = _derive_workspace_pick_query(phase=phase, session=session)
                if user_query:
                    params["user_query"] = user_query
                    changed = True
            if not params.get("conversation_context"):
                conversation_context = _derive_conversation_context(session)
                if conversation_context:
                    params["conversation_context"] = conversation_context
                    changed = True
            if not params.get("candidates"):
                candidates = _build_workspace_execution_candidates(
                    workspace_id=phase.target_workspace_id
                    or getattr(session, "workspace_id", None),
                    project_id=project_id,
                )
                if candidates:
                    params["candidates"] = candidates
                    changed = True

        if changed:
            phase.input_params = params
            if item is not None:
                item["input_params"] = dict(params)
                if phase.tool_name is None and phase.preferred_engine:
                    item["preferred_engine"] = phase.preferred_engine


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


def _derive_workspace_pick_query(*, phase: Any, session: Any) -> Optional[str]:
    phase_text = " ".join(
        filter(None, [phase.name, getattr(phase, "description", "") or ""])
    ).strip()
    if phase_text:
        return phase_text

    agenda = getattr(session, "agenda", None) or []
    if isinstance(agenda, list):
        for item in agenda:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _derive_conversation_context(session: Any) -> str:
    agenda = getattr(session, "agenda", None) or []
    if not isinstance(agenda, list):
        return ""
    agenda_lines = [str(item).strip() for item in agenda if str(item).strip()]
    return "\n".join(agenda_lines[:5])


def _build_workspace_execution_candidates(
    *,
    workspace_id: Optional[str],
    project_id: Optional[str],
    limit: int = DEFAULT_EXECUTION_CANDIDATE_LIMIT,
) -> List[Dict[str, Any]]:
    if not workspace_id:
        return []

    try:
        tasks = TasksStore().list_tasks_by_workspace(workspace_id, limit=limit * 5)
    except Exception:
        return []

    candidates: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    for task in tasks:
        task_type = getattr(task, "task_type", None)
        if task_type not in EXECUTION_CANDIDATE_TASK_TYPES:
            continue

        pack_id = getattr(task, "pack_id", None)
        if not pack_id or pack_id in EXECUTION_CANDIDATE_EXCLUDED_PACKS:
            continue

        status_obj = getattr(task, "status", None)
        status = getattr(status_obj, "value", status_obj)
        if status in {"pending", "planned"}:
            continue

        task_project_id = getattr(task, "project_id", None)
        if project_id and task_project_id and task_project_id == project_id:
            continue

        payload = task_to_payload(task)
        execution_id = payload.get("execution_id") or payload.get("id")
        if not execution_id or execution_id in seen_ids:
            continue

        candidate = dict(payload)
        candidate["execution_id"] = execution_id
        candidate.setdefault("id", payload.get("id") or execution_id)
        candidate.setdefault("playbook_code", payload.get("pack_id") or pack_id)
        candidate.setdefault("status", status)
        candidate.setdefault("created_at", payload.get("created_at"))

        seen_ids.add(execution_id)
        candidates.append(candidate)
        if len(candidates) >= limit:
            break

    return candidates
