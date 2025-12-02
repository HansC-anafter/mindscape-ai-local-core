"""
Task Status Fix Service

Fixes tasks that have execution_context.status = "completed" but task.status = "running".
This happens when PlaybookRunExecutor didn't properly update task status.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.conversation.task_manager import TaskManager
from backend.app.services.conversation.plan_builder import PlanBuilder
from backend.app.services.i18n_service import get_i18n_service

logger = logging.getLogger(__name__)


class TaskStatusFixService:
    """Service to fix task status inconsistencies"""

    def __init__(self, store: Optional[MindscapeStore] = None):
        """
        Initialize TaskStatusFixService

        Args:
            store: MindscapeStore instance (optional, will create if not provided)
        """
        self.store = store or MindscapeStore()
        self.tasks_store = TasksStore(self.store.db_path)
        self.timeline_items_store = TimelineItemsStore(self.store.db_path)

        plan_builder = PlanBuilder(
            store=self.store,
            default_locale="en"
        )

        from backend.app.services.playbook_runner import PlaybookRunner
        playbook_runner = PlaybookRunner()

        self.task_manager = TaskManager(
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            plan_builder=plan_builder,
            artifacts_store=None,
            playbook_runner=playbook_runner,
            default_locale="en"
        )

    def find_inconsistent_tasks(
        self,
        workspace_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Task]:
        """
        Find tasks with inconsistent status

        Returns tasks where:
        - task.status = "running"
        - execution_context.status = "completed", "succeeded", or "failed"

        Args:
            workspace_id: Filter by workspace ID (optional)
            limit: Maximum number of tasks to return (optional)

        Returns:
            List of inconsistent tasks
        """
        tasks = self.tasks_store.list_tasks_by_workspace(
            workspace_id=workspace_id,
            status=TaskStatus.RUNNING,
            limit=limit
        )

        inconsistent_tasks = []
        for task in tasks:
            if not task.execution_context:
                continue

            exec_context = task.execution_context
            if isinstance(exec_context, dict):
                context_status = exec_context.get("status")
                if context_status in ["completed", "succeeded", "failed"]:
                    inconsistent_tasks.append(task)

        return inconsistent_tasks

    def fix_task(
        self,
        task: Task,
        create_timeline_item: bool = True
    ) -> Dict[str, Any]:
        """
        Fix a single task's status

        Args:
            task: Task to fix
            create_timeline_item: Whether to create timeline item (default: True)

        Returns:
            Dict with fix results
        """
        if not task.execution_context:
            return {
                "task_id": task.id,
                "fixed": False,
                "reason": "No execution_context"
            }

        exec_context = task.execution_context
        if not isinstance(exec_context, dict):
            return {
                "task_id": task.id,
                "fixed": False,
                "reason": "execution_context is not a dict"
            }

        context_status = exec_context.get("status")
        if context_status not in ["completed", "succeeded", "failed"]:
            return {
                "task_id": task.id,
                "fixed": False,
                "reason": f"execution_context.status is '{context_status}', not 'completed', 'succeeded', or 'failed'"
            }

        try:
            playbook_code = exec_context.get("playbook_code") or task.pack_id or "unknown"

            if context_status in ["completed", "succeeded"]:
                new_status = TaskStatus.SUCCEEDED
                execution_result = {
                    "status": "completed",
                    "playbook_code": playbook_code,
                    "execution_id": task.execution_id or task.id,
                    "title": exec_context.get("playbook_name") or playbook_code,
                    "summary": f"Completed {playbook_code} execution",
                    "result": task.result or {}
                }
            else:
                new_status = TaskStatus.FAILED
                error_msg = exec_context.get("error") or "Execution failed"
                execution_result = {
                    "status": "failed",
                    "playbook_code": playbook_code,
                    "execution_id": task.execution_id or task.id,
                    "error": error_msg,
                    "title": f"Failed: {playbook_code}",
                    "summary": error_msg
                }

            completed_at = datetime.utcnow()
            if task.completed_at:
                completed_at = task.completed_at
            elif exec_context.get("completed_at"):
                try:
                    completed_at = datetime.fromisoformat(exec_context["completed_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            self.tasks_store.update_task(
                task.id,
                execution_context=exec_context,
                status=new_status,
                completed_at=completed_at,
                error=execution_result.get("error")
            )

            result = {
                "task_id": task.id,
                "fixed": True,
                "old_status": task.status.value,
                "new_status": new_status.value,
                "playbook_code": playbook_code,
                "timeline_item_created": False
            }

            if create_timeline_item:
                try:
                    timeline_item = self.task_manager.create_timeline_item_from_task(
                        task=task,
                        execution_result=execution_result,
                        playbook_code=playbook_code
                    )
                    if timeline_item:
                        result["timeline_item_created"] = True
                        result["timeline_item_id"] = timeline_item.id
                except Exception as e:
                    logger.warning(f"Failed to create timeline item for task {task.id}: {e}")
                    result["timeline_item_error"] = str(e)

            logger.info(f"Fixed task {task.id}: {task.status.value} -> {new_status.value}")
            return result

        except Exception as e:
            logger.error(f"Failed to fix task {task.id}: {e}", exc_info=True)
            return {
                "task_id": task.id,
                "fixed": False,
                "error": str(e)
            }

    def fix_all_inconsistent_tasks(
        self,
        workspace_id: Optional[str] = None,
        create_timeline_items: bool = True,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fix all inconsistent tasks

        Args:
            workspace_id: Filter by workspace ID (optional)
            create_timeline_items: Whether to create timeline items (default: True)
            limit: Maximum number of tasks to process (optional)

        Returns:
            Dict with fix summary
        """
        inconsistent_tasks = self.find_inconsistent_tasks(
            workspace_id=workspace_id,
            limit=limit
        )

        if not inconsistent_tasks:
            return {
                "total_found": 0,
                "total_fixed": 0,
                "total_failed": 0,
                "results": []
            }

        results = []
        fixed_count = 0
        failed_count = 0

        for task in inconsistent_tasks:
            result = self.fix_task(task, create_timeline_item=create_timeline_items)
            results.append(result)
            if result.get("fixed"):
                fixed_count += 1
            else:
                failed_count += 1

        summary = {
            "total_found": len(inconsistent_tasks),
            "total_fixed": fixed_count,
            "total_failed": failed_count,
            "results": results
        }

        logger.info(f"Task status fix completed: {fixed_count} fixed, {failed_count} failed out of {len(inconsistent_tasks)} total")
        return summary

