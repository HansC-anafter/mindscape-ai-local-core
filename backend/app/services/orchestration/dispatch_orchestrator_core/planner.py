"""Pure planning helpers for DispatchOrchestrator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
        if _hydrate_workspace_id(params=params, phase=phase, session=session):
            changed = True

        playbook_code = extract_playbook_code(getattr(phase, "preferred_engine", None))

        if playbook_code == "cis_mind_identity":
            document_content = _build_phase_context_text(
                phase=phase,
                phase_map=phase_map,
                session=session,
                include_phase_params=True,
            )
            if not params.get("document_content") and document_content:
                params["document_content"] = document_content
                changed = True
            if not params.get("document_type"):
                params["document_type"] = "brief"
                changed = True
            if not params.get("target_language"):
                params["target_language"] = "zh-TW"
                changed = True

        if playbook_code == "cis_behavior_identity":
            brand_context = _build_phase_context_text(
                phase=phase,
                phase_map=phase_map,
                session=session,
                include_phase_params=True,
            )
            if not params.get("brand_context") and brand_context:
                params["brand_context"] = brand_context
                changed = True

        if playbook_code == "week1_feed_factory":
            lens_id = getattr(session, "lens_id", None)
            if not params.get("lens_id") and lens_id:
                params["lens_id"] = lens_id
                changed = True
            if not params.get("topic_materials"):
                topic_materials = _build_topic_materials(
                    phase=phase,
                    phase_map=phase_map,
                    session=session,
                )
                if topic_materials:
                    params["topic_materials"] = topic_materials
                    changed = True

        if playbook_code == "ig_post_generation":
            source_content = _build_phase_context_text(
                phase=phase,
                phase_map=phase_map,
                session=session,
                include_phase_params=True,
            )
            if not params.get("source_content") and source_content:
                params["source_content"] = source_content
                changed = True

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


@dataclass
class _ActionItemPhaseAdapter:
    id: str
    name: str
    description: str = ""
    preferred_engine: Optional[str] = None
    target_workspace_id: Optional[str] = None
    tool_name: Optional[str] = None
    input_params: Optional[Dict[str, Any]] = None
    depends_on: Optional[List[str]] = None


def normalize_action_item_inputs(
    *,
    action_items: List[Dict[str, Any]],
    session: Any,
) -> None:
    """Hydrate action_items before policy gate sees them.

    MeetingEngine runs policy validation before DispatchOrchestrator executes,
    so the gate cannot rely on later phase normalization. Adapt the current
    action_items into lightweight phase-like objects and reuse the same planner
    hydration logic against the live pre-dispatch payload.
    """
    adapted_phases: List[_ActionItemPhaseAdapter] = []
    for index, item in enumerate(action_items, start=1):
        if not isinstance(item, dict):
            continue

        preferred_engine = _coerce_action_item_engine(item)
        raw_blocked_by = item.get("blocked_by")
        depends_on = raw_blocked_by if isinstance(raw_blocked_by, list) else None
        adapted_phases.append(
            _ActionItemPhaseAdapter(
                id=str(item.get("intent_id") or item.get("title") or f"item-{index}"),
                name=str(item.get("title") or f"item-{index}"),
                description=str(item.get("description") or ""),
                preferred_engine=preferred_engine,
                target_workspace_id=item.get("target_workspace_id"),
                tool_name=item.get("tool_name"),
                input_params=(
                    dict(item.get("input_params"))
                    if isinstance(item.get("input_params"), dict)
                    else {}
                ),
                depends_on=list(depends_on or []),
            )
        )

    if not adapted_phases:
        return

    normalize_phase_inputs(
        phases=adapted_phases,
        action_items=action_items,
        session=session,
    )

    for adapted_phase, item in zip(adapted_phases, action_items):
        if adapted_phase.input_params:
            item["input_params"] = dict(adapted_phase.input_params)


def _coerce_action_item_engine(item: Dict[str, Any]) -> Optional[str]:
    raw_engine = item.get("engine")
    if isinstance(raw_engine, str) and raw_engine.strip():
        return raw_engine.strip()

    playbook_code = item.get("playbook_code")
    if isinstance(playbook_code, str) and playbook_code.strip():
        return f"playbook:{playbook_code.strip()}"

    tool_name = item.get("tool_name")
    if isinstance(tool_name, str) and tool_name.strip():
        return f"tool:{tool_name.strip()}"

    return None


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


def _hydrate_workspace_id(
    *, params: Dict[str, Any], phase: Any, session: Any
) -> bool:
    """Fill workspace_id for playbook phases that omitted it."""
    if params.get("workspace_id"):
        return False
    workspace_id = phase.target_workspace_id or getattr(session, "workspace_id", None)
    if not workspace_id:
        return False
    params["workspace_id"] = workspace_id
    return True


def _clean_string_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    cleaned: List[str] = []
    seen: Set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _serialize_context_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, dict)):
        if not value:
            return None
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return None


def _collect_upstream_context(*, phase: Any, phase_map: Dict[str, Any]) -> List[str]:
    snippets: List[str] = []
    visited: Set[str] = set()

    def visit(phase_id: str) -> None:
        if phase_id in visited:
            return
        visited.add(phase_id)
        upstream = phase_map.get(phase_id)
        if upstream is None:
            return

        if getattr(upstream, "name", None):
            snippets.append(f"phase={upstream.name}")
        description = getattr(upstream, "description", None)
        if isinstance(description, str) and description.strip():
            snippets.append(f"description={description.strip()}")

        params = upstream.input_params or {}
        for key in (
            "document_content",
            "brand_context",
            "source_content",
            "query",
            "topic",
        ):
            serialized = _serialize_context_value(params.get(key))
            if serialized:
                snippets.append(f"{key}={serialized}")

        for dep_id in upstream.depends_on or []:
            visit(dep_id)

    for dep_id in phase.depends_on or []:
        visit(dep_id)

    deduped: List[str] = []
    seen: Set[str] = set()
    for snippet in snippets:
        if snippet in seen:
            continue
        seen.add(snippet)
        deduped.append(snippet)
    return deduped


def _build_phase_context_text(
    *,
    phase: Any,
    phase_map: Dict[str, Any],
    session: Any,
    include_phase_params: bool = False,
) -> Optional[str]:
    sections: List[str] = []

    agenda = _clean_string_list(getattr(session, "agenda", None))
    if agenda:
        sections.append("Meeting agenda:\n- " + "\n- ".join(agenda))

    success_criteria = _clean_string_list(getattr(session, "success_criteria", None))
    if success_criteria:
        sections.append("Success criteria:\n- " + "\n- ".join(success_criteria))

    phase_lines: List[str] = []
    if getattr(phase, "name", None):
        phase_lines.append(f"Current phase: {phase.name}")
    description = getattr(phase, "description", None)
    if isinstance(description, str) and description.strip():
        phase_lines.append(f"Phase description: {description.strip()}")
    if getattr(session, "lens_id", None):
        phase_lines.append(f"Lens ID: {session.lens_id}")
    if phase_lines:
        sections.append("\n".join(phase_lines))

    upstream_context = _collect_upstream_context(phase=phase, phase_map=phase_map)
    if upstream_context:
        sections.append("Upstream context:\n- " + "\n- ".join(upstream_context))

    if include_phase_params:
        param_lines: List[str] = []
        for key, value in sorted((phase.input_params or {}).items()):
            if key in {
                "workspace_id",
                "lens_id",
                "document_content",
                "brand_context",
                "source_content",
                "topic_materials",
                "deliverable_name",
                "deliverable_path",
            }:
                continue
            serialized = _serialize_context_value(value)
            if serialized:
                param_lines.append(f"{key}: {serialized}")
        if param_lines:
            sections.append("Requested parameters:\n- " + "\n- ".join(param_lines))

    if not sections:
        return None
    return "\n\n".join(sections)


def _build_topic_materials(
    *, phase: Any, phase_map: Dict[str, Any], session: Any
) -> Dict[str, Any]:
    topic_materials: Dict[str, Any] = {}

    agenda = _clean_string_list(getattr(session, "agenda", None))
    if agenda:
        topic_materials["agenda"] = agenda

    success_criteria = _clean_string_list(getattr(session, "success_criteria", None))
    if success_criteria:
        topic_materials["success_criteria"] = success_criteria

    if getattr(session, "lens_id", None):
        topic_materials["lens_id"] = session.lens_id

    if getattr(phase, "name", None):
        topic_materials["phase_name"] = phase.name
    description = getattr(phase, "description", None)
    if isinstance(description, str) and description.strip():
        topic_materials["phase_description"] = description.strip()

    brief = _build_phase_context_text(
        phase=phase,
        phase_map=phase_map,
        session=session,
        include_phase_params=True,
    )
    if brief:
        topic_materials["brief"] = brief

    upstream_context = _collect_upstream_context(phase=phase, phase_map=phase_map)
    if upstream_context:
        topic_materials["upstream_context"] = upstream_context

    return topic_materials


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
        "source_intent_id": getattr(phase, "source_intent_id", None)
        or action_item.get("intent_id"),
        "priority": getattr(phase, "priority", None) or action_item.get("priority"),
    }
