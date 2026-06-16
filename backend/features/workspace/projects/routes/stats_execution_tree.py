"""Execution tree projection helpers for workspace project routes."""

import logging
from collections import defaultdict
from typing import Any, Dict

from fastapi import HTTPException

from backend.app.models.workspace import ExecutionSession
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager

logger = logging.getLogger(__name__)


async def build_project_execution_tree(
    *,
    workspace_id: str,
    project_id: str,
    store: MindscapeStore,
) -> Dict[str, Any]:
    """
    Get execution tree for a project, grouped by playbook.

    Returns executions grouped by playbook_code with statistics.
    """
    from backend.app.services.stores.tasks_store import TasksStore

    project_manager = ProjectManager(store)
    project = await project_manager.get_project(project_id, workspace_id=workspace_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tasks_store = TasksStore(db_path=store.db_path)

    # Get all execution tasks for this workspace
    all_execution_tasks = tasks_store.list_executions_by_workspace(
        workspace_id=workspace_id, limit=500
    )

    # Filter executions by project_id (with fallbacks to avoid losing data when context is missing)
    project_executions = []
    for task in all_execution_tasks:
        execution_context = task.execution_context or {}
        exec_project_id = execution_context.get("project_id") or (
            task.params or {}
        ).get("project_id")

        # If project_id is explicitly set and does not match, skip
        if exec_project_id and exec_project_id != project_id:
            continue

        # Fallback: if missing, assume this execution belongs to the requested project
        if not exec_project_id:
            exec_project_id = project_id
            execution_context["project_id"] = project_id

        # Ensure project name is present in context
        execution_context["project_name"] = (
            execution_context.get("project_name") or project.title
        )

        try:
            execution = ExecutionSession.from_task(task)
            execution_dict = (
                execution.model_dump()
                if hasattr(execution, "model_dump")
                else execution
            )
            if isinstance(execution_dict, dict):
                execution_dict["status"] = task.status.value
                execution_dict["created_at"] = (
                    task.created_at.isoformat() if task.created_at else None
                )
                execution_dict["started_at"] = (
                    task.started_at.isoformat() if task.started_at else None
                )
                execution_dict["completed_at"] = (
                    task.completed_at.isoformat() if task.completed_at else None
                )
                execution_dict["project_id"] = exec_project_id
                execution_dict["project_name"] = project.title

                # Keep execution_context in the nested task as well, so frontend can read project_id/project_name
                if isinstance(execution_dict.get("task"), dict):
                    task_ctx = execution_dict["task"].get("execution_context") or {}
                    task_ctx.setdefault("project_id", exec_project_id)
                    task_ctx.setdefault("project_name", project.title)
                    execution_dict["task"]["execution_context"] = task_ctx

                    # Optimization: Strip heavy result from nested task
                    if "result" in execution_dict["task"]:
                        execution_dict["task"]["result"] = None

                # Critical Optimization: Strip heavy fields before returning to frontend
                execution_dict["result"] = None
                # We can keep execution_context as it's usually small, but result is huge (18MB+)

            project_executions.append(execution_dict)
        except Exception as e:
            logger.warning(
                f"Failed to create ExecutionSession from task {task.id}: {e}"
            )

    # Group executions by playbook_code
    playbook_groups = defaultdict(
        lambda: {
            "playbookCode": "",
            "playbookName": "",
            "executions": [],
            "stats": {
                "running": 0,
                "paused": 0,
                "queued": 0,
                "completed": 0,
                "failed": 0,
            },
        }
    )

    for exec_dict in project_executions:
        playbook_code = exec_dict.get("playbook_code") or "unknown"
        playbook_name = exec_dict.get("playbook_title") or playbook_code

        group = playbook_groups[playbook_code]
        group["playbookCode"] = playbook_code
        group["playbookName"] = playbook_name
        group["executions"].append(exec_dict)

        # Update stats
        status = exec_dict.get("status", "").lower()
        if status == "running":
            group["stats"]["running"] += 1
        elif status == "paused":
            group["stats"]["paused"] += 1
        elif status in ["queued", "pending"]:
            group["stats"]["queued"] += 1
        elif status in ["succeeded", "completed", "done"]:
            group["stats"]["completed"] += 1
        elif status in ["failed", "error"]:
            group["stats"]["failed"] += 1

    # Convert to list and sort executions within each group
    playbook_groups_list = []
    for playbook_code, group in playbook_groups.items():
        # Sort executions by created_at (earliest first)
        group["executions"].sort(
            key=lambda e: (e.get("created_at") or e.get("started_at") or "1970-01-01")
        )
        playbook_groups_list.append(group)

    # Sort groups by playbook_code
    playbook_groups_list.sort(key=lambda g: g["playbookCode"])

    return {
        "playbookGroups": playbook_groups_list,
        "projectId": project_id,
        "projectName": project.title,
    }
