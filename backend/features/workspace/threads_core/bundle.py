"""Thread bundle aggregation helpers."""

import logging
from typing import List

from backend.app.models.thread_bundle import (
    ThreadBundle,
    ThreadDeliverable,
    ThreadOverview,
    ThreadReferenceResponse,
    ThreadRun,
    ThreadSource,
)
from backend.app.models.workspace import ConversationThread
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.features.workspace.threads_core.validation import get_thread_or_404

logger = logging.getLogger("backend.features.workspace.threads")


def _artifact_type_value(artifact) -> str:
    return (
        artifact.artifact_type.value
        if hasattr(artifact.artifact_type, "value")
        else str(artifact.artifact_type)
    )


def _reference_response(reference) -> ThreadReferenceResponse:
    return ThreadReferenceResponse(
        id=reference.id,
        source_type=reference.source_type,
        uri=reference.uri,
        title=reference.title,
        snippet=reference.snippet,
        reason=reference.reason,
        created_at=reference.created_at.isoformat(),
        pinned_by=reference.pinned_by or "user",
    )


def _deliverables_from_artifacts(artifacts) -> list[ThreadDeliverable]:
    deliverables = []
    for artifact in artifacts:
        source = "playbook" if artifact.playbook_code else "ai_generated"
        if artifact.metadata and "source" in artifact.metadata:
            source = artifact.metadata["source"]

        source_event_id = (
            artifact.metadata.get("source_event_id", "") if artifact.metadata else ""
        )
        if not source_event_id and artifact.execution_id:
            source_event_id = artifact.execution_id

        status = artifact.metadata.get("status", "draft") if artifact.metadata else "draft"
        if artifact.sync_state == "synced":
            status = "final"

        deliverables.append(
            ThreadDeliverable(
                id=artifact.id,
                title=artifact.title or "Untitled",
                artifact_type=_artifact_type_value(artifact),
                source=source,
                source_event_id=source_event_id,
                status=status,
                updated_at=(
                    artifact.updated_at.isoformat()
                    if artifact.updated_at
                    else artifact.created_at.isoformat()
                ),
            )
        )
    return deliverables


def _runs_from_playbook_executions(executions, artifacts) -> list[ThreadRun]:
    runs = []
    for execution in executions:
        deliverable_ids = [
            artifact.id for artifact in artifacts if artifact.execution_id == execution.id
        ]
        steps_completed = 0
        steps_total = 0
        if execution.metadata:
            steps_completed = execution.metadata.get("steps_completed", 0)
            steps_total = execution.metadata.get("steps_total", 0)

        duration_ms = None
        if execution.created_at and execution.updated_at:
            delta = execution.updated_at - execution.created_at
            duration_ms = int(delta.total_seconds() * 1000)

        runs.append(
            ThreadRun(
                id=execution.id,
                playbook_name=execution.playbook_code,
                status=execution.status,
                started_at=execution.created_at.isoformat(),
                duration_ms=duration_ms,
                steps_completed=steps_completed,
                steps_total=steps_total,
                deliverable_ids=deliverable_ids,
            )
        )
    return runs


def _task_status_value(task) -> str:
    return task.status.value if hasattr(task.status, "value") else str(task.status)


def _append_task_runs(
    *,
    runs: list[ThreadRun],
    workspace_id: str,
    thread_id: str,
    artifacts,
    executions,
) -> None:
    try:
        tasks_store = TasksStore()
        task_runs = tasks_store.list_tasks_by_thread(
            workspace_id=workspace_id,
            thread_id=thread_id,
            limit=20,
            exclude_cancelled=True,
        )
        playbook_exec_ids = {execution.id for execution in executions}
        for task in task_runs:
            if task.execution_id in playbook_exec_ids or task.id in playbook_exec_ids:
                continue

            status_map = {
                "SUCCEEDED": "completed",
                "FAILED": "failed",
                "RUNNING": "running",
                "PENDING": "running",
            }
            run_status = status_map.get(_task_status_value(task), "running")
            result_summary = None
            storage_ref = None
            if task.result and isinstance(task.result, dict):
                result_summary = task.result.get("summary") or task.result.get(
                    "output", ""
                )
                storage_ref = task.result.get("storage_ref")

            duration_ms = None
            if task.result and isinstance(task.result, dict):
                duration_seconds = task.result.get("duration_seconds")
                if duration_seconds:
                    duration_ms = int(float(duration_seconds) * 1000)
            elif task.created_at and task.completed_at:
                delta = task.completed_at - task.created_at
                duration_ms = int(delta.total_seconds() * 1000)

            task_exec_id = task.execution_id or task.id
            deliverable_ids = [
                artifact.id for artifact in artifacts if artifact.execution_id == task_exec_id
            ]

            runs.append(
                ThreadRun(
                    id=task.id,
                    playbook_name=task.title or task.playbook_id or "Agent Task",
                    status=run_status,
                    started_at=(task.started_at or task.created_at).isoformat(),
                    duration_ms=duration_ms,
                    steps_completed=1 if run_status == "completed" else 0,
                    steps_total=1,
                    deliverable_ids=deliverable_ids,
                    result_summary=result_summary,
                    storage_ref=storage_ref,
                )
            )
    except Exception as e:
        logger.warning(f"Failed to load task dispatch runs for thread {thread_id}: {e}")


def get_thread_sources(thread: ConversationThread) -> List[ThreadSource]:
    sources = []
    if not thread.pinned_scope or not isinstance(thread.pinned_scope, dict):
        return sources

    scope_type = thread.pinned_scope.get("type", "")
    if scope_type == "site":
        sources.append(
            ThreadSource(
                id=thread.pinned_scope.get("identifier", ""),
                type="wordpress_site",
                identifier=thread.pinned_scope.get("identifier", ""),
                display_name=thread.pinned_scope.get("display_name", ""),
                permissions=["read", "write"],
                sync_status="connected",
            )
        )
    elif scope_type == "obsidian_vault":
        sources.append(
            ThreadSource(
                id=thread.pinned_scope.get("identifier", ""),
                type="obsidian_vault",
                identifier=thread.pinned_scope.get("identifier", ""),
                display_name=thread.pinned_scope.get("display_name", ""),
                permissions=["read", "write"],
                sync_status="connected",
            )
        )
    return sources


def build_thread_bundle(
    *,
    workspace_id: str,
    thread_id: str,
    store: MindscapeStore,
) -> ThreadBundle:
    thread = get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    artifacts = store.artifacts.get_by_thread(
        workspace_id=workspace_id, thread_id=thread_id, limit=100
    )
    deliverables = _deliverables_from_artifacts(artifacts)

    refs = store.thread_references.get_by_thread(
        workspace_id=workspace_id, thread_id=thread_id, limit=100
    )
    references = [_reference_response(reference) for reference in refs]

    executions = store.playbook_executions.get_by_thread(
        workspace_id=workspace_id, thread_id=thread_id, limit=20
    )
    runs = _runs_from_playbook_executions(executions, artifacts)
    _append_task_runs(
        runs=runs,
        workspace_id=workspace_id,
        thread_id=thread_id,
        artifacts=artifacts,
        executions=executions,
    )
    runs.sort(key=lambda run: run.started_at, reverse=True)

    status = "in_progress"
    if deliverables and all(deliverable.status == "final" for deliverable in deliverables):
        status = "delivered"
    elif not deliverables and not references:
        status = "pending_data"

    return ThreadBundle(
        thread_id=thread_id,
        overview=ThreadOverview(
            title=thread.title,
            status=status,
            summary=thread.metadata.get("summary") if thread.metadata else None,
            project_id=thread.project_id,
            pinned_scope=thread.pinned_scope,
        ),
        deliverables=deliverables,
        references=references,
        runs=runs,
        sources=get_thread_sources(thread),
    )
