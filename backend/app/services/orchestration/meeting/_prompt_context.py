"""Context-building helpers for ``MeetingPromptsMixin``."""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.mindscape import EventType

logger = logging.getLogger(__name__)


def build_project_context(meeting: Any) -> str:
    """Fetch project data and recent activity to provide meeting context."""
    if not meeting.project_id:
        return ""

    parts: List[str] = []
    try:
        project = meeting.store.get_project(meeting.project_id)
        if project:
            parts.append(f"Project: {getattr(project, 'title', meeting.project_id)}")
            project_type = getattr(project, "type", None)
            if project_type:
                parts.append(f"Type: {project_type}")
            project_state = getattr(project, "state", None)
            if project_state:
                parts.append(f"State: {project_state}")
            project_metadata = getattr(project, "metadata", None)
            if project_metadata and isinstance(project_metadata, dict):
                summary_keys = [
                    "goal",
                    "goals",
                    "description",
                    "brief",
                    "scope",
                    "deliverables",
                    "requirements",
                ]
                for key in summary_keys:
                    value = project_metadata.get(key)
                    if value:
                        parts.append(f"{key.capitalize()}: {value}")
    except Exception as exc:
        logger.warning("Failed to fetch project for meeting context: %s", exc)

    try:
        recent_events = meeting.store.get_events_by_project(meeting.project_id, limit=10)
        if recent_events:
            activity_lines = []
            for event in recent_events[:5]:
                event_type = getattr(event, "event_type", "")
                event_type_str = (
                    event_type.value if hasattr(event_type, "value") else str(event_type)
                )
                channel = str(getattr(event, "channel", "") or "").lower()
                if channel == "meeting" or event_type_str in {
                    "meeting_start",
                    "meeting_round",
                    "meeting_end",
                    "state_vector_computed",
                    "decision_required",
                    "action_item",
                    "agent_turn",
                    "decision_proposal",
                    "decision_final",
                }:
                    continue
                payload = getattr(event, "payload", {}) or {}
                summary = payload.get("message") or payload.get("title") or str(event_type)
                if not isinstance(summary, str):
                    summary = str(summary)
                if (
                    "Meeting Minutes" in summary
                    or "Awaiting user confirmation" in summary
                    or "HIGH risk level" in summary
                ):
                    continue
                if len(summary) > 120:
                    summary = summary[:120] + "..."
                activity_lines.append(f"  - {summary}")
            if activity_lines:
                parts.append("Recent project activity:\n" + "\n".join(activity_lines))
    except Exception as exc:
        logger.warning("Failed to fetch project events for meeting: %s", exc)

    return "\n".join(parts) if parts else ""


def format_workspace_identity(ws: Any, parts: List[str]) -> None:
    """Append workspace identity lines from blueprint + suggestions."""
    has_identity = False
    blueprint = getattr(ws, "workspace_blueprint", None)
    if blueprint:
        instruction = getattr(blueprint, "instruction", None)
        if instruction:
            persona = getattr(instruction, "persona", "") or ""
            if persona:
                parts.append(f"    Identity: {persona[:120]}")
                has_identity = True
            goals = getattr(instruction, "goals", []) or []
            if goals:
                parts.append(f"    Goals: {'; '.join(goal[:60] for goal in goals[:3])}")
                has_identity = True

    suggestion_history = getattr(ws, "suggestion_history", []) or []
    if suggestion_history:
        latest = suggestion_history[-1] if suggestion_history else {}
        suggestions = latest.get("suggestions", [])[:3]
        if suggestions:
            titles = [suggestion.get("title", "?")[:50] for suggestion in suggestions]
            parts.append(f"    Recent capabilities: {', '.join(titles)}")

    data_sources = getattr(ws, "data_sources", None) or {}
    if data_sources and isinstance(data_sources, dict):
        asset_lines = []
        for pack, info in sorted(
            data_sources.items(),
            key=lambda item: item[1].get("last_run", ""),
            reverse=True,
        ):
            runs = info.get("total_runs", 0)
            last = (info.get("last_run") or "")[:10]
            produces = info.get("produces", [])
            if produces and isinstance(produces, list):
                for produced in produces:
                    label = produced.get("label", produced.get("type", pack))
                    line = f"      - {label}: {runs} runs"
                    if last:
                        line += f", last {last}"
                    asset_lines.append(line)
            else:
                summary = info.get("last_result_summary", "")
                line = f"      - {pack}: {runs} runs"
                if last:
                    line += f", last {last}"
                if summary:
                    line += f" ({summary[:60]})"
                asset_lines.append(line)
        if asset_lines:
            parts.append("    Data assets (completed):")
            parts.extend(asset_lines[:10])
            has_identity = True

    if not has_identity:
        parts.append("    (no identity info available)")


def append_workspace_identity(
    meeting: Any,
    ws_store: Any,
    ws_id: str,
    parts: List[str],
) -> None:
    """Look up a workspace by ID and append its identity card."""
    try:
        import asyncio

        loop = asyncio.get_event_loop()
        if loop.is_running():
            ws = None
            try:
                ws = ws_store.get_workspace_sync(ws_id)
            except AttributeError:
                pass
            if ws:
                format_workspace_identity(ws, parts)
                return
        parts.append("    (identity lookup unavailable)")
    except Exception:
        parts.append("    (identity lookup failed)")


def build_asset_map_context(meeting: Any) -> str:
    """Build workspace group asset map for cross-workspace dispatch routing."""
    workspace = getattr(meeting, "workspace", None)
    if not workspace:
        return ""

    try:
        from backend.app.services.stores.postgres.workspaces_store import (
            PostgresWorkspacesStore,
        )

        parts: List[str] = []
        seen_workspace_ids = set()
        current_workspace_id = getattr(workspace, "id", None)

        group_id = getattr(workspace, "group_id", None)
        if group_id:
            from backend.app.services.stores.postgres.workspace_group_store import (
                PostgresWorkspaceGroupStore,
            )

            group_store = PostgresWorkspaceGroupStore()
            group = group_store.get(group_id)
            if group:
                parts.append(f"Workspace Group: {group.display_name} ({group.id})")
                workspace_role = getattr(workspace, "workspace_role", None) or "cell"
                parts.append(f"Current workspace role: {workspace_role}")

                ws_store = PostgresWorkspacesStore()
                for ws_id, role in group.role_map.items():
                    seen_workspace_ids.add(ws_id)
                    workspace_label = f"  [{role}] {ws_id}"
                    if ws_id == current_workspace_id:
                        workspace_label += " (current)"
                    parts.append(workspace_label)
                    append_workspace_identity(meeting, ws_store, ws_id, parts)

        ws_store = PostgresWorkspacesStore()
        discoverable = ws_store.list_discoverable_workspaces(visibility="discoverable")
        extra = [
            ws
            for ws in discoverable
            if ws.id not in seen_workspace_ids and ws.id != current_workspace_id
        ]
        if extra:
            parts.append("")
            parts.append("Discoverable Workspaces (outside group):")
            for ws in extra:
                parts.append(f"  [discoverable] {ws.id} — {ws.title}")
                format_workspace_identity(ws, parts)

        return "\n".join(parts) if parts else ""
    except Exception as exc:
        logger.warning("Failed to build asset map context: %s", exc)
        return ""


def build_lens_context(meeting: Any) -> str:
    """Build lens context block for prompt injection."""
    lens = getattr(meeting, "_effective_lens", None)
    if not lens:
        return ""

    parts: List[str] = []
    try:
        parts.append(f"Active Lens: {lens.global_preset_name}")
        parts.append(f"Lens Hash: {lens.hash}")
        engaged_nodes = [node for node in lens.nodes if node.state.value != "off"]
        emphasized = [node for node in lens.nodes if node.state.value == "emphasize"]
        if emphasized:
            parts.append("Emphasized dimensions:")
            for node in emphasized[:10]:
                parts.append(f"  - {node.node_label} (scope: {node.effective_scope})")
        if engaged_nodes:
            parts.append(f"Total active dimensions: {len(engaged_nodes)}")
    except Exception as exc:
        logger.warning("Failed to build lens context: %s", exc)

    return "\n".join(parts) if parts else ""


def build_previous_decisions_context(meeting: Any) -> str:
    """Build previous meeting decisions context from DECISION_FINAL events."""
    if not meeting.project_id:
        return ""

    parts: List[str] = []
    try:
        workspace_id = getattr(meeting.workspace, "id", None) or meeting.session.workspace_id
        session_store = getattr(meeting, "session_store", None)
        if not session_store:
            return ""

        previous_sessions = session_store.list_by_workspace(
            workspace_id=workspace_id,
            project_id=meeting.project_id,
            limit=2,
        )
        previous = None
        for session in previous_sessions:
            if session.id != meeting.session.id and not session.is_active:
                previous = session
                break
        if not previous:
            return ""

        decision_events = []
        try:
            all_session_events = meeting.store.get_events_by_meeting_session(
                meeting_session_id=previous.id,
                limit=50,
            )
            decision_events = [
                event
                for event in (all_session_events or [])
                if (
                    getattr(event, "event_type", None) == EventType.DECISION_FINAL
                    or getattr(getattr(event, "event_type", None), "value", None)
                    == "decision_final"
                )
            ][:10]
        except Exception:
            pass

        if decision_events:
            parts.append("Previous meeting decisions:")
            for event in decision_events[:5]:
                payload = getattr(event, "payload", {}) or {}
                decision_text = payload.get("decision", "")
                if decision_text:
                    round_number = payload.get("round_number", "?")
                    parts.append(f"  - [R{round_number}] {decision_text[:200]}")
        elif previous.minutes_md:
            minutes_snippet = previous.minutes_md[:800]
            if len(previous.minutes_md) > 800:
                minutes_snippet += "\n... (truncated)"
            parts.append("Previous meeting summary:")
            parts.append(minutes_snippet)

        if previous.action_items:
            parts.append("Previous action items:")
            for item in previous.action_items[:5]:
                title = item.get("title", "Untitled")
                status = item.get("status", "pending")
                parts.append(f"  - {title} [{status}]")
    except Exception as exc:
        logger.warning("Failed to build previous decisions context: %s", exc)

    return "\n".join(parts) if parts else ""


def build_workflow_evidence_context(meeting: Any) -> str:
    """Build a compact workflow-evidence packet for meeting deliberation."""
    workspace_id = getattr(getattr(meeting, "workspace", None), "id", None) or getattr(
        getattr(meeting, "session", None), "workspace_id", None
    )
    if not workspace_id:
        return ""

    project_id = getattr(meeting, "project_id", None) or getattr(
        getattr(meeting, "session", None), "project_id", None
    )
    thread_id = getattr(meeting, "thread_id", None) or getattr(
        getattr(meeting, "session", None), "thread_id", None
    )

    tasks_store = _resolve_meeting_store(
        meeting,
        "_tasks_store_for_evidence",
        lambda: getattr(meeting, "tasks_store", None),
    )
    artifact_store = _resolve_meeting_store(
        meeting,
        "_artifacts_store_for_evidence",
        _build_artifact_store,
    )
    stage_results_store = _resolve_meeting_store(
        meeting,
        "_stage_results_store_for_evidence",
        _build_stage_results_store,
    )
    intent_logs_store = _resolve_meeting_store(
        meeting,
        "_intent_logs_store_for_evidence",
        _build_intent_logs_store,
    )
    governance_store = _resolve_meeting_store(
        meeting,
        "_governance_store_for_evidence",
        _build_governance_store,
    )
    lens_patch_store = _resolve_meeting_store(
        meeting,
        "_lens_patch_store_for_evidence",
        _build_lens_patch_store,
    )
    meeting_profile = _infer_workflow_evidence_profile(meeting)

    parts: List[str] = [
        "Use these recent workflow materials as supporting evidence when they help the meeting agenda."
    ]
    sections: Dict[str, List[str]] = {}

    tasks, selected_scope = _list_recent_execution_tasks(
        meeting=meeting,
        tasks_store=tasks_store,
        workspace_id=workspace_id,
        project_id=project_id,
        thread_id=thread_id,
        meeting_profile=meeting_profile,
    )
    execution_ids = [
        str(getattr(task, "execution_id", "")).strip()
        for task in tasks
        if str(getattr(task, "execution_id", "")).strip()
    ]

    sections["Recent execution outcomes"] = [
        _format_task_execution_line(task) for task in tasks[:3]
    ]

    if stage_results_store and execution_ids:
        stage_candidates: List[Any] = []
        for execution_id in execution_ids[:3]:
            try:
                stage_results = stage_results_store.list_stage_results(
                    execution_id=execution_id,
                    limit=4,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to list stage results for workflow evidence (%s): %s",
                    execution_id,
                    exc,
                )
                continue
            stage_candidates.extend(stage_results)
        ranked_stage_results = _sort_by_score(
            stage_candidates,
            lambda item: _score_stage_result(item, meeting_profile),
        )
        sections["Recent stage checkpoints"] = [
            _format_stage_result_line(stage_result)
            for stage_result in ranked_stage_results[:3]
        ]

    artifact_candidates: List[Any] = []
    if artifact_store and execution_ids:
        for execution_id in execution_ids[:3]:
            try:
                artifact = artifact_store.get_by_execution_id(execution_id)
            except Exception as exc:
                logger.warning(
                    "Failed to fetch artifact for workflow evidence (%s): %s",
                    execution_id,
                    exc,
                )
                continue
            if artifact is not None:
                artifact_candidates.append(artifact)
    elif artifact_store and thread_id and hasattr(artifact_store, "list_artifacts_by_thread"):
        try:
            thread_artifacts = artifact_store.list_artifacts_by_thread(
                workspace_id=workspace_id,
                thread_id=thread_id,
                limit=6,
            )
        except Exception as exc:
            logger.warning(
                "Failed to list thread artifacts for workflow evidence (%s): %s",
                thread_id,
                exc,
            )
            thread_artifacts = []
        artifact_candidates.extend(thread_artifacts)
    ranked_artifacts = _sort_by_score(
        artifact_candidates,
        lambda item: _score_artifact(item, meeting_profile),
    )
    sections["Recent artifacts"] = [
        _format_artifact_line(artifact) for artifact in ranked_artifacts[:3]
    ]

    if governance_store and execution_ids:
        governance_candidates: List[Dict[str, Any]] = []
        for execution_id in execution_ids[:3]:
            try:
                decisions = governance_store.list_decisions_for_execution(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    limit=4,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to list governance decisions for workflow evidence (%s): %s",
                    execution_id,
                    exc,
                )
                continue
            governance_candidates.extend(decisions)
        ranked_governance = _sort_by_score(
            governance_candidates,
            lambda item: _score_governance_decision(item, meeting_profile),
        )
        sections["Recent governance outcomes"] = [
            _format_governance_decision_line(decision)
            for decision in ranked_governance[:3]
        ]

    if intent_logs_store:
        try:
            intent_logs = intent_logs_store.list_intent_logs(
                workspace_id=workspace_id,
                project_id=project_id,
                limit=8,
            )
        except Exception as exc:
            logger.warning("Failed to list intent logs for workflow evidence: %s", exc)
            intent_logs = []
        ranked_intent_logs = _sort_by_score(
            intent_logs,
            lambda item: _score_intent_log(item, meeting_profile),
        )
        sections["Recent intent routing"] = [
            _format_intent_log_line(intent_log)
            for intent_log in ranked_intent_logs[:3]
        ]

    if lens_patch_store:
        lens_id = getattr(getattr(meeting, "_effective_lens", None), "global_preset_id", None)
        if lens_id:
            try:
                latest_patch = lens_patch_store.get_latest_for_lens(lens_id)
            except Exception as exc:
                logger.warning(
                    "Failed to load lens patch for workflow evidence (%s): %s",
                    lens_id,
                    exc,
                )
                latest_patch = None
            if latest_patch is not None:
                sections["Latest lens continuity signal"] = [
                    _format_lens_patch_line(latest_patch)
                ]

    section_order = _workflow_section_order(meeting_profile)
    bounded_sections, diagnostics = _apply_workflow_evidence_budget(
        sections=sections,
        section_order=section_order,
        meeting_profile=meeting_profile,
        selected_scope=selected_scope,
    )

    for title in section_order:
        _append_section(parts, title, bounded_sections.get(title, []))

    if len(parts) <= 1:
        setattr(meeting, "_workflow_evidence_diagnostics", diagnostics)
        return ""

    diagnostics["rendered"] = True
    diagnostics["rendered_section_count"] = len(
        [title for title in section_order if bounded_sections.get(title)]
    )
    setattr(meeting, "_workflow_evidence_diagnostics", diagnostics)
    return "\n".join(parts)


def _resolve_meeting_store(
    meeting: Any,
    attr_name: str,
    factory: Callable[[], Any],
) -> Optional[Any]:
    existing = getattr(meeting, attr_name, None)
    if existing is not None:
        return existing
    try:
        store = factory()
    except Exception as exc:
        logger.debug("Workflow evidence store init failed for %s: %s", attr_name, exc)
        return None
    if store is not None:
        setattr(meeting, attr_name, store)
    return store


def _build_artifact_store() -> Any:
    from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore

    return PostgresArtifactsStore()


def _build_stage_results_store() -> Any:
    from backend.app.services.stores.stage_results_store import StageResultsStore

    return StageResultsStore()


def _build_intent_logs_store() -> Any:
    from backend.app.services.stores.postgres.intent_logs_store import (
        PostgresIntentLogsStore,
    )

    return PostgresIntentLogsStore()


def _build_governance_store() -> Any:
    from backend.app.services.governance.governance_store import GovernanceStore

    return GovernanceStore()


def _build_lens_patch_store() -> Any:
    from backend.app.services.stores.lens_patch_store import LensPatchStore

    return LensPatchStore()


def _list_recent_execution_tasks(
    *,
    meeting: Any,
    tasks_store: Any,
    workspace_id: str,
    project_id: Optional[str],
    thread_id: Optional[str],
    meeting_profile: str,
) -> tuple[List[Any], str]:
    if tasks_store is None:
        return [], "none"

    tasks: List[Any] = []
    selected_scope = "none"
    fetch_attempts = []
    if thread_id and hasattr(tasks_store, "list_tasks_by_thread"):
        fetch_attempts.append(
            (
                "thread",
                lambda: tasks_store.list_tasks_by_thread(
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    limit=8,
                    exclude_cancelled=True,
                ),
            )
        )
    if project_id and hasattr(tasks_store, "list_executions_by_project"):
        fetch_attempts.append(
            (
                "project",
                lambda: tasks_store.list_executions_by_project(
                    workspace_id=workspace_id,
                    project_id=project_id,
                    limit=8,
                ),
            )
        )
    if hasattr(tasks_store, "list_executions_by_workspace"):
        fetch_attempts.append(
            (
                "workspace",
                lambda: tasks_store.list_executions_by_workspace(
                    workspace_id=workspace_id,
                    limit=8,
                ),
            )
        )

    for scope_label, fetch in fetch_attempts:
        try:
            tasks = fetch() or []
        except Exception as exc:
            logger.warning(
                "Failed to list execution tasks for workflow evidence (%s): %s",
                scope_label,
                exc,
            )
            continue
        if tasks:
            selected_scope = scope_label
            break

    filtered: List[Any] = []
    seen_keys = set()
    for task in tasks:
        task_type = str(getattr(task, "task_type", "") or "")
        execution_id = str(getattr(task, "execution_id", "") or "")
        if task_type != "execution" and not execution_id:
            continue
        dedupe_key = execution_id or str(getattr(task, "id", "") or "")
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        filtered.append(task)
        if len(filtered) >= 8:
            break
    return (
        _sort_by_score(
            filtered,
            lambda item: _score_task_execution(item, meeting_profile),
        )[:4],
        selected_scope,
    )


def _append_section(parts: List[str], title: str, lines: List[str]) -> None:
    clean_lines = [line for line in lines if line]
    if not clean_lines:
        return
    parts.append(f"{title}:")
    parts.extend(clean_lines[:3])


def _infer_workflow_evidence_profile(meeting: Any) -> str:
    meeting_type = str(getattr(getattr(meeting, "session", None), "meeting_type", "") or "").lower()
    agenda = getattr(getattr(meeting, "session", None), "agenda", None) or []
    agenda_text = " ".join(str(item).lower() for item in agenda)
    combined = f"{meeting_type} {agenda_text}"

    if any(token in combined for token in ("meta", "reflection", "retrospective", "retro")):
        return "reflection"
    if any(token in combined for token in ("review", "inspect", "audit", "evaluate", "feedback")):
        return "review"
    if any(token in combined for token in ("decision", "approve", "approval", "choose", "selection", "direction")):
        return "decision"
    return "general"


def _workflow_section_order(meeting_profile: str) -> List[str]:
    if meeting_profile == "review":
        return [
            "Recent stage checkpoints",
            "Recent governance outcomes",
            "Recent artifacts",
            "Recent execution outcomes",
            "Recent intent routing",
            "Latest lens continuity signal",
        ]
    if meeting_profile == "decision":
        return [
            "Recent governance outcomes",
            "Recent intent routing",
            "Recent execution outcomes",
            "Recent stage checkpoints",
            "Recent artifacts",
            "Latest lens continuity signal",
        ]
    if meeting_profile == "reflection":
        return [
            "Latest lens continuity signal",
            "Recent governance outcomes",
            "Recent intent routing",
            "Recent execution outcomes",
            "Recent stage checkpoints",
            "Recent artifacts",
        ]
    return [
        "Recent execution outcomes",
        "Recent stage checkpoints",
        "Recent governance outcomes",
        "Recent artifacts",
        "Recent intent routing",
        "Latest lens continuity signal",
    ]


def _workflow_section_budgets(meeting_profile: str) -> tuple[Dict[str, int], int]:
    if meeting_profile == "review":
        return (
            {
                "Recent stage checkpoints": 3,
                "Recent governance outcomes": 2,
                "Recent artifacts": 2,
                "Recent execution outcomes": 2,
                "Recent intent routing": 1,
                "Latest lens continuity signal": 1,
            },
            9,
        )
    if meeting_profile == "decision":
        return (
            {
                "Recent governance outcomes": 3,
                "Recent intent routing": 2,
                "Recent execution outcomes": 2,
                "Recent stage checkpoints": 1,
                "Recent artifacts": 1,
                "Latest lens continuity signal": 1,
            },
            8,
        )
    if meeting_profile == "reflection":
        return (
            {
                "Latest lens continuity signal": 1,
                "Recent governance outcomes": 2,
                "Recent intent routing": 2,
                "Recent execution outcomes": 2,
                "Recent stage checkpoints": 1,
                "Recent artifacts": 1,
            },
            8,
        )
    return (
        {
            "Recent execution outcomes": 3,
            "Recent stage checkpoints": 2,
            "Recent governance outcomes": 2,
            "Recent artifacts": 2,
            "Recent intent routing": 1,
            "Latest lens continuity signal": 1,
        },
        9,
    )


def _apply_workflow_evidence_budget(
    *,
    sections: Dict[str, List[str]],
    section_order: List[str],
    meeting_profile: str,
    selected_scope: str,
) -> tuple[Dict[str, List[str]], Dict[str, Any]]:
    section_limits, total_line_budget = _workflow_section_budgets(meeting_profile)
    bounded_sections: Dict[str, List[str]] = {}
    candidate_counts = {
        title: len([line for line in sections.get(title, []) if line])
        for title in section_order
    }
    selected_counts: Dict[str, int] = {}
    dropped_counts: Dict[str, int] = {}
    remaining_budget = total_line_budget

    for title in section_order:
        if remaining_budget <= 0:
            bounded_sections[title] = []
            selected_counts[title] = 0
            dropped_counts[title] = candidate_counts.get(title, 0)
            continue
        clean_lines = [line for line in sections.get(title, []) if line]
        section_budget = section_limits.get(title, 0)
        allowed = min(len(clean_lines), section_budget, remaining_budget)
        bounded_sections[title] = clean_lines[:allowed]
        selected_counts[title] = allowed
        dropped_counts[title] = max(len(clean_lines) - allowed, 0)
        remaining_budget -= allowed

    total_candidate_count = sum(candidate_counts.values())
    total_dropped_count = sum(dropped_counts.values())
    selected_line_count = sum(selected_counts.values())
    budget_utilization_ratio = (
        round(selected_line_count / total_line_budget, 3)
        if total_line_budget > 0
        else 0.0
    )

    diagnostics: Dict[str, Any] = {
        "profile": meeting_profile,
        "scope": selected_scope,
        "section_order": section_order,
        "section_limits": section_limits,
        "total_line_budget": total_line_budget,
        "total_candidate_count": total_candidate_count,
        "total_dropped_count": total_dropped_count,
        "candidate_counts": candidate_counts,
        "selected_counts": selected_counts,
        "dropped_counts": dropped_counts,
        "selected_line_count": selected_line_count,
        "budget_utilization_ratio": budget_utilization_ratio,
        "rendered": False,
    }
    return bounded_sections, diagnostics


def _sort_by_score(items: List[Any], score_fn: Callable[[Any], float]) -> List[Any]:
    return sorted(items, key=score_fn, reverse=True)


def _score_task_execution(task: Any, meeting_profile: str) -> float:
    score = _recency_score(
        getattr(task, "completed_at", None) or getattr(task, "created_at", None)
    )
    status = getattr(getattr(task, "status", None), "value", None) or str(
        getattr(task, "status", "")
    )
    if status == "succeeded":
        score += 5.0
    elif status == "running":
        score += 2.0
    if _extract_task_summary(task):
        score += 2.0
    result = getattr(task, "result", None) or {}
    if isinstance(result, dict) and isinstance(result.get("execution_trace"), dict):
        score += 1.5
    params = getattr(task, "params", None) or {}
    if isinstance(params, dict) and any(params.get(key) for key in ("title", "description", "task")):
        score += 0.5
    if meeting_profile == "decision":
        score += 1.0 if status == "succeeded" else 0.0
    if meeting_profile == "reflection":
        score += 1.0 if isinstance(result, dict) and result.get("execution_trace") else 0.0
    return score


def _score_stage_result(stage_result: Any, meeting_profile: str) -> float:
    score = _recency_score(getattr(stage_result, "created_at", None))
    if getattr(stage_result, "requires_review", False):
        score += 4.0
    review_status = str(getattr(stage_result, "review_status", "") or "")
    if review_status in {"pending", "needs_review"}:
        score += 3.0
    if getattr(stage_result, "preview", None):
        score += 1.5
    if getattr(stage_result, "artifact_id", None):
        score += 1.0
    if meeting_profile == "review":
        score += 3.0
    return score


def _score_artifact(artifact: Any, meeting_profile: str) -> float:
    score = _recency_score(
        getattr(artifact, "updated_at", None) or getattr(artifact, "created_at", None)
    )
    if getattr(artifact, "summary", None):
        score += 1.5
    metadata = getattr(artifact, "metadata", None) or {}
    landing = metadata.get("landing") if isinstance(metadata, dict) else {}
    attachments_count = landing.get("attachments_count") if isinstance(landing, dict) else 0
    if isinstance(attachments_count, int) and attachments_count > 0:
        score += min(float(attachments_count), 3.0)
    artifact_type = getattr(getattr(artifact, "artifact_type", None), "value", None) or str(
        getattr(artifact, "artifact_type", "")
    )
    if artifact_type in {"draft", "docx", "post", "code"}:
        score += 1.0
    if meeting_profile == "review":
        score += 1.0
    return score


def _score_governance_decision(decision: Dict[str, Any], meeting_profile: str) -> float:
    score = _recency_score(_coerce_datetime(decision.get("timestamp")))
    approved = bool(decision.get("approved"))
    score += 3.0 if not approved else 1.5
    if decision.get("reason"):
        score += 2.0
    layer = str(decision.get("layer") or "")
    if layer in {"policy", "approval", "risk"}:
        score += 2.0
    if decision.get("playbook_code"):
        score += 1.0
    if meeting_profile in {"review", "decision"}:
        score += 2.0
    return score


def _score_intent_log(intent_log: Any, meeting_profile: str) -> float:
    score = _recency_score(getattr(intent_log, "timestamp", None))
    final_decision = getattr(intent_log, "final_decision", None) or {}
    if final_decision.get("playbook_code") or final_decision.get("selected_playbook_code"):
        score += 2.0
    if final_decision.get("requires_user_approval"):
        score += 3.0
    if getattr(intent_log, "user_override", None):
        score += 4.0
    pipeline_steps = getattr(intent_log, "pipeline_steps", None) or {}
    if isinstance(pipeline_steps, dict) and pipeline_steps:
        score += 1.0
    if meeting_profile == "decision":
        score += 2.0
    return score


def _recency_score(value: Any) -> float:
    dt = _coerce_datetime(value)
    if dt is None:
        return 0.0
    age_hours = max((datetime.now(dt.tzinfo) - dt).total_seconds() / 3600.0, 0.0)
    return max(0.0, 6.0 - min(age_hours, 6.0))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _format_task_execution_line(task: Any) -> str:
    status = getattr(getattr(task, "status", None), "value", None) or str(
        getattr(task, "status", "unknown")
    )
    pack_id = str(getattr(task, "pack_id", "unknown") or "unknown")
    execution_id = str(getattr(task, "execution_id", "") or "")
    result = getattr(task, "result", None)
    summary = _extract_task_summary(task)
    trace_note = ""
    if isinstance(result, dict) and isinstance(result.get("execution_trace"), dict):
        trace_note = " trace=yes"
    execution_label = f" exec={execution_id[:8]}" if execution_id else ""
    summary_label = f" :: {summary}" if summary else ""
    return f"  - [{status}] {pack_id}{execution_label}{trace_note}{summary_label}"


def _extract_task_summary(task: Any) -> str:
    result = getattr(task, "result", None)
    if isinstance(result, dict):
        for key in ("summary", "message", "result_summary", "title", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 160)
        trace_payload = result.get("execution_trace")
        if isinstance(trace_payload, dict):
            for key in ("output_summary", "task_description"):
                value = trace_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return _shorten(value.strip(), 160)
    params = getattr(task, "params", None)
    if isinstance(params, dict):
        for key in ("title", "description", "task", "prompt"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 160)
    return ""


def _format_stage_result_line(stage_result: Any) -> str:
    stage_name = str(getattr(stage_result, "stage_name", "stage") or "stage")
    result_type = str(getattr(stage_result, "result_type", "result") or "result")
    review_status = getattr(stage_result, "review_status", None)
    preview = getattr(stage_result, "preview", None)
    if not preview and isinstance(getattr(stage_result, "content", None), dict):
        for key in ("summary", "message", "title", "result_summary"):
            value = stage_result.content.get(key)
            if isinstance(value, str) and value.strip():
                preview = value.strip()
                break
    review_label = f" review={review_status}" if review_status else ""
    preview_label = f" :: {_shorten(str(preview), 160)}" if preview else ""
    return f"  - {stage_name}/{result_type}{review_label}{preview_label}"


def _format_artifact_line(artifact: Any) -> str:
    artifact_type = getattr(getattr(artifact, "artifact_type", None), "value", None) or str(
        getattr(artifact, "artifact_type", "artifact")
    )
    title = _shorten(str(getattr(artifact, "title", "Artifact") or "Artifact"), 72)
    summary = str(getattr(artifact, "summary", "") or "").strip()
    metadata = getattr(artifact, "metadata", None) or {}
    landing = metadata.get("landing") if isinstance(metadata, dict) else {}
    attachments_count = (
        landing.get("attachments_count")
        if isinstance(landing, dict)
        else None
    )
    attachment_label = (
        f" attachments={attachments_count}"
        if isinstance(attachments_count, int)
        else ""
    )
    summary_label = f" :: {_shorten(summary, 140)}" if summary else ""
    return f"  - {title} [{artifact_type}]{attachment_label}{summary_label}"


def _format_governance_decision_line(decision: Dict[str, Any]) -> str:
    approved = bool(decision.get("approved"))
    layer = str(decision.get("layer") or "governance")
    status = "approved" if approved else "blocked"
    playbook_code = decision.get("playbook_code")
    reason = str(decision.get("reason") or "").strip()
    playbook_label = f" playbook={playbook_code}" if playbook_code else ""
    reason_label = f" :: {_shorten(reason, 140)}" if reason else ""
    return f"  - [{status}] {layer}{playbook_label}{reason_label}"


def _format_intent_log_line(intent_log: Any) -> str:
    final_decision = getattr(intent_log, "final_decision", None) or {}
    route = (
        final_decision.get("playbook_code")
        or final_decision.get("task_domain")
        or final_decision.get("interaction_type")
        or "unspecified"
    )
    override_label = (
        " override=yes"
        if getattr(intent_log, "user_override", None)
        else ""
    )
    raw_input = _shorten(str(getattr(intent_log, "raw_input", "") or "").strip(), 140)
    channel = str(getattr(intent_log, "channel", "unknown") or "unknown")
    return f"  - [{channel}] route={route}{override_label} :: {raw_input}"


def _format_lens_patch_line(patch: Any) -> str:
    status = getattr(getattr(patch, "status", None), "value", None) or str(
        getattr(patch, "status", "unknown")
    )
    confidence = getattr(patch, "confidence", None)
    delta = getattr(patch, "delta", None) or {}
    delta_keys = list(delta.keys())[:3] if isinstance(delta, dict) else []
    delta_label = ", ".join(delta_keys) if delta_keys else "lens delta recorded"
    confidence_label = (
        f" confidence={float(confidence):.2f}"
        if isinstance(confidence, (int, float))
        else ""
    )
    return f"  - [{status}]{confidence_label} :: {_shorten(delta_label, 140)}"


def _shorten(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
