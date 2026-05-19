"""Legacy task projection helpers for meeting action items."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.workspace import Task, TaskStatus

logger = logging.getLogger(__name__)


class ActionItemTaskProjectionMixin:
    async def _land_action_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Create a task projection for an action item."""
        item.setdefault("meeting_session_id", self.session.id)
        item.setdefault("execution_id", None)
        item.setdefault("task_id", None)

        item["task_id"] = self._create_action_task(item)
        item["landing_status"] = "task_created" if item.get("task_id") else "planned"

        return item

    def _create_action_task(self, item: Dict[str, Any]) -> Optional[str]:
        """Create a Task record for an action item."""
        if not self.tasks_store:
            return None
        try:
            task_id = str(uuid.uuid4())
            target_ws = item.get("target_workspace_id") or self.session.workspace_id

            if item.get("playbook_code"):
                task_type = "playbook_execution"
                pack_id = item["playbook_code"]
            elif item.get("tool_name"):
                task_type = "tool_execution"
                pack_id = item["tool_name"]
            else:
                logger.debug(
                    "Skipping task creation for unmatched action item: %s",
                    item.get("title", "?"),
                )
                return None

            task = Task(
                id=task_id,
                workspace_id=target_ws,
                message_id=(self._events[-1].id if self._events else str(uuid.uuid4())),
                execution_id=item.get("execution_id"),
                project_id=self.project_id,
                pack_id=pack_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                params={
                    "meeting_session_id": self.session.id,
                    "thread_id": getattr(self.session, "thread_id", None),
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "priority": item.get("priority"),
                    "tool_name": item.get("tool_name"),
                    "input_params": item.get("input_params"),
                },
                result=None,
                execution_context={
                    "trigger_source": "meeting_engine",
                    "meeting_session_id": self.session.id,
                    "thread_id": getattr(self.session, "thread_id", None),
                    "tool_name": item.get("tool_name"),
                    "inputs": item.get("input_params") or {},
                },
                created_at=datetime.now(timezone.utc),
            )
            self.tasks_store.create_task(task)
            return task_id
        except Exception as exc:
            logger.warning(
                "MeetingEngine failed to create action task: %s", exc, exc_info=True
            )
            return None
