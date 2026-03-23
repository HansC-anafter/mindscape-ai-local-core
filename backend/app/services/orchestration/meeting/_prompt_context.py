"""Context-building helpers for ``MeetingPromptsMixin``."""

import logging
from typing import Any, Dict, List

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
