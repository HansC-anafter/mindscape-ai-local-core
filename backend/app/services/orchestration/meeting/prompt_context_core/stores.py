"""Workflow evidence store and task retrieval helpers."""

import logging
from typing import Any, Callable, List, Optional

from backend.app.services.orchestration.meeting.prompt_context_core.budgeting import (
    _workflow_evidence_requires_thread_scope,
)
from backend.app.services.orchestration.meeting.prompt_context_core.scoring import (
    _score_task_execution,
    _sort_by_score,
)

logger = logging.getLogger(__name__)


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
    thread_bounded = _workflow_evidence_requires_thread_scope(meeting)
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
    if not thread_bounded and project_id and hasattr(tasks_store, "list_executions_by_project"):
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
    if not thread_bounded and hasattr(tasks_store, "list_executions_by_workspace"):
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
        selected_scope if selected_scope != "none" else (
            "thread_bounded_empty" if thread_bounded else selected_scope
        ),
    )
