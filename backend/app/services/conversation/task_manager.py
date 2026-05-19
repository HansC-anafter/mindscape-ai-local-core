"""Task and TimelineItem lifecycle manager facade."""

from typing import Any, Dict, List, Optional

from backend.app.models.workspace import Task, TimelineItem
from backend.app.services.artifact_extractor import ArtifactExtractor
from backend.app.services.conversation.task_manager_core import (
    create_artifact_mind_event as create_artifact_mind_event_helper,
    retry_timeline_item_artifact_creation,
    update_artifact_latest_markers as update_artifact_latest_markers_helper,
)
from backend.app.services.conversation.task_manager_core.graph_nodes import (
    create_graph_node_for_task as create_graph_node_for_task_helper,
)
from backend.app.services.conversation.task_manager_core.lifecycle import (
    create_timeline_item_from_task as create_timeline_item_from_task_helper,
    mark_task_as_displayed as mark_task_as_displayed_helper,
    mark_task_notification_sent,
)
from backend.app.services.conversation.task_manager_core.status_polling import (
    check_and_update_task_status as check_and_update_task_status_helper,
)
from backend.app.services.conversation.task_manager_core.timeouts import (
    TASK_TIMEOUT_MINUTES,
    check_and_timeout_tasks as check_and_timeout_tasks_helper,
)
from backend.app.services.execution_core.clock import utc_now
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.stores.artifacts_store import ArtifactsStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.timeline_items_store import TimelineItemsStore


class TaskManager:
    """Manage task lifecycle while delegating implementation to core helpers."""

    def __init__(
        self,
        tasks_store: TasksStore,
        timeline_items_store: TimelineItemsStore,
        plan_builder,
        playbook_runner,
        default_locale: str = "en",
        artifacts_store: ArtifactsStore = None,
        store=None,
    ):
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.plan_builder = plan_builder
        self.playbook_runner = playbook_runner
        self.i18n = get_i18n_service(default_locale=default_locale)
        self.artifacts_store = artifacts_store
        self.store = store
        self.artifact_extractor = ArtifactExtractor(store)

    async def create_timeline_item_from_task(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        playbook_code: str,
    ) -> Optional[TimelineItem]:
        """Create TimelineItem from completed task."""
        return await create_timeline_item_from_task_helper(
            manager=self,
            task=task,
            execution_result=execution_result,
            playbook_code=playbook_code,
        )

    def _mark_task_notification_sent(self, task_id: str) -> None:
        """Mark task as notification sent."""
        mark_task_notification_sent(manager=self, task_id=task_id)

    async def _create_graph_node_for_task(
        self,
        task: Task,
        timeline_item: TimelineItem,
        playbook_code: str,
        execution_result: Dict[str, Any],
    ) -> None:
        """Update or create the completed task graph node."""
        await create_graph_node_for_task_helper(
            task=task,
            timeline_item=timeline_item,
            playbook_code=playbook_code,
            execution_result=execution_result,
        )

    def mark_task_as_displayed(self, task_id: str) -> None:
        """Mark task as displayed by the frontend."""
        mark_task_as_displayed_helper(manager=self, task_id=task_id)

    async def _create_artifact_mind_event(
        self,
        artifact,
        task: Task,
        execution_result: Dict[str, Any],
    ) -> None:
        await create_artifact_mind_event_helper(
            store=self.store,
            artifact=artifact,
            task=task,
            execution_result=execution_result,
            utc_now_fn=utc_now,
        )

    async def retry_artifact_creation(self, timeline_item_id: str) -> Dict[str, Any]:
        return await retry_timeline_item_artifact_creation(
            store=self.store,
            tasks_store=self.tasks_store,
            timeline_items_store=self.timeline_items_store,
            artifacts_store=self.artifacts_store,
            artifact_extractor=self.artifact_extractor,
            timeline_item_id=timeline_item_id,
            update_latest_markers_fn=self._update_artifact_latest_markers,
            create_mind_event_fn=self._create_artifact_mind_event,
        )

    def _update_artifact_latest_markers(
        self,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        new_artifact_id: str,
    ) -> None:
        update_artifact_latest_markers_helper(
            artifacts_store=self.artifacts_store,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type,
            new_artifact_id=new_artifact_id,
        )

    async def check_and_update_task_status(
        self,
        task: Task,
        execution_id: Optional[str],
        playbook_code: str,
    ) -> None:
        """Check playbook execution status and update task and timeline stores."""
        await check_and_update_task_status_helper(
            manager=self,
            task=task,
            execution_id=execution_id,
            playbook_code=playbook_code,
        )

    def check_and_timeout_tasks(
        self,
        timeout_minutes: int = TASK_TIMEOUT_MINUTES,
    ) -> List[str]:
        """Check running tasks and fail those that exceeded the timeout window."""
        return check_and_timeout_tasks_helper(
            manager=self,
            timeout_minutes=timeout_minutes,
        )
