"""Execution, stats, and artifact helpers for workspace project cards."""

import logging
from types import SimpleNamespace
from typing import Any, Dict

from fastapi import HTTPException

from backend.app.models.project import Project
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager

from .stats_card_events import (
    build_card_events,
    build_project_metadata_and_meeting_summary,
)
from .stats_card_flow import build_playbook_card_context, ensure_project_flow_exists

logger = logging.getLogger(__name__)


async def build_project_card_payload(
    *,
    workspace_id: str,
    project_id: str,
    workspace: Workspace,
    store: MindscapeStore,
) -> Dict[str, Any]:
    """Build the complete project card response payload."""
    project_manager = ProjectManager(store)
    project = await project_manager.get_project(project_id, workspace_id=workspace_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    await ensure_project_flow_exists(
        project=project,
        workspace=workspace,
        store=store,
        project_id=project_id,
    )
    execution_context = await collect_project_card_executions(
        workspace_id=workspace_id,
        project_id=project_id,
        project=project,
        store=store,
    )
    playbook_context = build_playbook_card_context(
        project=project,
        store=store,
        completed_executions=execution_context["completed_executions"],
    )
    card_events = await build_card_events(
        events_store=execution_context["events_store"],
        project_id=project_id,
    )
    metadata_context = build_project_metadata_and_meeting_summary(
        workspace_id=workspace_id,
        project_id=project_id,
        project=project,
    )

    return {
        "projectId": project.id,
        "projectName": project.title,
        "storyThreadId": (
            project.metadata.get("story_thread_id") if project.metadata else None
        ),
        "mindLensId": metadata_context["mind_lens_id"],
        "mindLensName": metadata_context["mind_lens_name"],
        "status": metadata_context["status"],
        "lastActivity": (
            project.updated_at.isoformat()
            if hasattr(project.updated_at, "isoformat")
            else str(project.updated_at)
        ),
        "stats": {
            "totalPlaybooks": playbook_context["total_playbooks"],
            "runningExecutions": len(execution_context["running_executions"]),
            "pendingConfirmations": len(execution_context["pending_confirmations"]),
            "completedExecutions": len(execution_context["completed_executions"]),
            "artifactCount": len(execution_context["artifacts"]),
        },
        "progress": {
            "current": playbook_context["progress_current"],
            "label": playbook_context["progress_label"],
        },
        "playbooks": playbook_context["playbook_list"],
        "recentEvents": card_events,
        "meeting": metadata_context["meeting_summary"],
    }


async def collect_project_card_executions(
    *,
    workspace_id: str,
    project_id: str,
    project: Project,
    store: MindscapeStore,
) -> Dict[str, Any]:
    """Collect executions and derived stats for the project card."""
    from backend.app.services.stores.events_store import EventsStore
    from backend.app.services.stores.tasks_store import TasksStore

    tasks_store = TasksStore(store.db_path)
    executions_store = store.playbook_executions
    events_store = EventsStore(store.db_path)

    # Direct query by project_id (optimized path)
    project_execution_tasks = tasks_store.list_executions_by_project(
        workspace_id=workspace_id, project_id=project_id, limit=500
    )
    logger.info(
        f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks for project {project_id} via direct query"
    )

    # Fallback: If no tasks found via project_id, try matching by playbook_code and project flow
    # This handles cases where old tasks don't have project_id set
    if not project_execution_tasks and project.flow_id:
        try:
            from backend.app.services.stores.playbook_flows_store import (
                PlaybookFlowsStore,
            )

            flows_store = PlaybookFlowsStore(store.db_path)
            flow = flows_store.get_flow(project.flow_id)
            if flow:
                flow_def = (
                    flow.flow_definition
                    if isinstance(flow.flow_definition, dict)
                    else {}
                )
                playbook_sequence = flow_def.get("playbook_sequence", [])
                if playbook_sequence:
                    # Get all execution tasks and filter by playbook_code
                    all_execution_tasks = tasks_store.list_executions_by_workspace(
                        workspace_id=workspace_id, limit=500
                    )
                    for task in all_execution_tasks:
                        execution_context = task.execution_context or {}
                        playbook_code = (
                            execution_context.get("playbook_code") or task.pack_id
                        )
                        if playbook_code in playbook_sequence:
                            project_execution_tasks.append(task)
                            # Update task with project_id for future queries
                            if not task.project_id:
                                # Note: We used to update the task here (write-on-read), but that causes
                                # synchronous DB writes which block the event loop.
                                # We now only update the in-memory object for display.
                                pass

                    logger.info(
                        f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks via playbook_code matching (fallback)"
                    )
        except Exception as e:
            logger.debug(f"Fallback matching failed: {e}")

    # Get events for this project to find execution IDs (for fallback)
    project_events = events_store.get_events_by_project(
        project_id=project_id, limit=200
    )

    # [REMOVED] Sync Full Table Scan (Fallback)
    # Optimized for performance: relying only on tasks_store.
    all_workspace_events = []

    # Convert execution tasks to execution objects
    project_executions = []
    logger.info(
        f"[ProjectCard] Found {len(project_execution_tasks)} execution tasks for project {project_id}"
    )
    for task in project_execution_tasks:
        try:
            # Create a simple execution dict from task (don't use ExecutionSession which may not exist)
            execution_context = task.execution_context or {}
            execution_dict = {
                "id": task.id,
                "execution_id": task.id,
                "status": task.status.value,
                "playbook_code": execution_context.get("playbook_code") or task.pack_id,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat()
                if task.completed_at
                else None,
                "project_id": project_id,
                "project_name": project.title,
                "task": {"id": task.id, "execution_context": execution_context},
            }
            project_executions.append(execution_dict)
            logger.info(
                f"[ProjectCard] Added execution {task.id[:8]} with status {task.status.value}, playbook_code={execution_dict['playbook_code']}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to create execution dict from task {task.id}: {e}",
                exc_info=True,
            )

    # Fallback: Extract unique execution IDs from events (if no tasks found)
    if not project_executions:
        execution_ids = set()
        for event in project_events:
            if event.payload and isinstance(event.payload, dict):
                exec_id = event.payload.get("execution_id")
                if exec_id:
                    execution_ids.add(exec_id)
            if event.entity_ids:
                for entity_id in event.entity_ids:
                    if entity_id and len(entity_id) == 36 and entity_id.count("-") == 4:
                        execution_ids.add(entity_id)

        # Also check workspace events for execution IDs
        for event in all_workspace_events:
            if event.payload and isinstance(event.payload, dict):
                exec_id = event.payload.get("execution_id")
                playbook_code = event.payload.get("playbook_code")
                if exec_id and playbook_code:
                    # Check if this playbook is part of the project's flow
                    if project.flow_id:
                        from backend.app.services.stores.playbook_flows_store import (
                            PlaybookFlowsStore,
                        )

                        flows_store = PlaybookFlowsStore(store.db_path)
                        flow = flows_store.get_flow(project.flow_id)
                        if flow:
                            flow_def = (
                                flow.flow_definition
                                if isinstance(flow.flow_definition, dict)
                                else {}
                            )
                            playbook_sequence = flow_def.get("playbook_sequence", [])
                            if playbook_code in playbook_sequence:
                                execution_ids.add(exec_id)
                    else:
                        execution_ids.add(exec_id)

        # Get executions by IDs
        for exec_id in execution_ids:
            exec_obj = executions_store.get_execution(exec_id)
            if exec_obj:
                project_executions.append(exec_obj)

    if not project_executions:
        # Count executions from workspace events
        execution_status_map = {}
        for event in all_workspace_events:
            if event.payload and isinstance(event.payload, dict):
                exec_id = event.payload.get("execution_id")
                playbook_code = event.payload.get("playbook_code")
                if exec_id and playbook_code:
                    # Include all executions from workspace events
                    # We'll filter by playbook_code matching project flow if flow exists
                    should_include = True
                    if project.flow_id:
                        try:
                            from backend.app.services.stores.playbook_flows_store import (
                                PlaybookFlowsStore,
                            )

                            flows_store = PlaybookFlowsStore(store.db_path)
                            flow = flows_store.get_flow(project.flow_id)
                            if flow:
                                flow_def = (
                                    flow.flow_definition
                                    if isinstance(flow.flow_definition, dict)
                                    else {}
                                )
                                playbook_sequence = flow_def.get(
                                    "playbook_sequence", []
                                )
                                if playbook_sequence:
                                    should_include = playbook_code in playbook_sequence
                        except:
                            # If flow lookup fails, include all
                            should_include = True

                    if should_include and exec_id not in execution_status_map:
                        execution_status_map[exec_id] = {
                            "playbook_code": playbook_code,
                            "status": "running",  # Default to running if not in DB
                        }

        # Create mock execution objects for stats calculation
        for exec_id, exec_data in execution_status_map.items():
            mock_exec = SimpleNamespace(
                id=exec_id,
                playbook_code=exec_data["playbook_code"],
                status=exec_data["status"],
                phase=None,
            )
            project_executions.append(mock_exec)

    (
        running_executions,
        completed_executions,
        pending_confirmations,
    ) = _calculate_execution_stats(project_executions)

    # Get artifacts count
    from backend.app.services.project.artifact_registry_service import (
        ArtifactRegistryService,
    )

    artifact_registry = ArtifactRegistryService(store)
    artifacts = await artifact_registry.list_artifacts(project_id=project_id)

    return {
        "project_executions": project_executions,
        "running_executions": running_executions,
        "completed_executions": completed_executions,
        "pending_confirmations": pending_confirmations,
        "artifacts": artifacts,
        "events_store": events_store,
    }


def _get_status(exec_obj: Any) -> str:
    if isinstance(exec_obj, dict):
        return exec_obj.get("status", "").lower()
    return (exec_obj.status if hasattr(exec_obj, "status") else "").lower()


def _calculate_execution_stats(
    project_executions: list[Any],
) -> tuple[list, list, list]:
    logger.info(
        f"[ProjectCard] Calculating stats from {len(project_executions)} executions"
    )
    for exec_obj in project_executions:
        status = _get_status(exec_obj)
        logger.debug(
            f"[ProjectCard] Execution {exec_obj.get('id', 'unknown')[:8] if isinstance(exec_obj, dict) else 'unknown'}: status={status}"
        )

    running_executions = [e for e in project_executions if _get_status(e) == "running"]
    completed_executions = [
        e
        for e in project_executions
        if _get_status(e) in ["completed", "succeeded", "done"]
    ]

    logger.info(
        f"[ProjectCard] Stats: running={len(running_executions)}, completed={len(completed_executions)}, total={len(project_executions)}"
    )

    # Get pending confirmations (executions waiting for confirmation)
    pending_confirmations = []
    for exec_obj in project_executions:
        status = _get_status(exec_obj)
        phase = None
        if isinstance(exec_obj, dict):
            phase = exec_obj.get("phase")
        elif hasattr(exec_obj, "phase"):
            phase = exec_obj.phase
        if status == "running" and phase and "waiting" in str(phase).lower():
            pending_confirmations.append(exec_obj)

    return running_executions, completed_executions, pending_confirmations
