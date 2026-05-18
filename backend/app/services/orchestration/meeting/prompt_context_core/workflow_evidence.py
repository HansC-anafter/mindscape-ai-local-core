"""Workflow evidence context assembly."""

import logging
from typing import Any, Dict, List

from backend.app.services.orchestration.meeting.prompt_context_core.budgeting import (
    _append_section,
    _apply_workflow_evidence_budget,
    _infer_workflow_evidence_profile,
    _workflow_evidence_requires_thread_scope,
    _workflow_section_order,
)
from backend.app.services.orchestration.meeting.prompt_context_core.formatters import (
    _format_artifact_line,
    _format_governance_decision_line,
    _format_intent_log_line,
    _format_lens_patch_line,
    _format_stage_result_line,
    _format_task_execution_line,
)
from backend.app.services.orchestration.meeting.prompt_context_core.scoring import (
    _score_artifact,
    _score_governance_decision,
    _score_intent_log,
    _score_stage_result,
    _sort_by_score,
)
from backend.app.services.orchestration.meeting.prompt_context_core.stores import (
    _build_artifact_store,
    _build_governance_store,
    _build_intent_logs_store,
    _build_lens_patch_store,
    _build_stage_results_store,
    _list_recent_execution_tasks,
    _resolve_meeting_store,
)

logger = logging.getLogger(__name__)


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
    thread_bounded = _workflow_evidence_requires_thread_scope(meeting)

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

    if intent_logs_store and not thread_bounded:
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

    if lens_patch_store and not thread_bounded:
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
