"""
Task Manager

Manages Task and TimelineItem lifecycle: creation, status updates, and polling.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional


from ...models.workspace import (
    Task,
    TaskStatus,
    TimelineItem,
)
from ...services.conversation.task_manager_core import (
    attach_artifact_to_timeline_item,
    create_artifact_mind_event as create_artifact_mind_event_helper,
    create_failed_execution_timeline_item,
    create_task_completion_timeline_item,
    create_timeout_timeline_item,
    retry_timeline_item_artifact_creation,
    update_artifact_latest_markers as update_artifact_latest_markers_helper,
)
from ...services.execution_core.clock import utc_now as _utc_now
from ...services.stores.tasks_store import TasksStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...services.stores.artifacts_store import ArtifactsStore
from ...services.stores.graph_changelog_store import GraphChangelogStore
from ...services.i18n_service import get_i18n_service
from backend.app.services.artifact_extractor import ArtifactExtractor

logger = logging.getLogger(__name__)

# Task timeout configuration
TASK_TIMEOUT_MINUTES = 5  # Tasks running longer than 5 minutes are considered timed out


class TaskManager:
    """
    Manages Task and TimelineItem lifecycle

    Handles:
    - Task creation and status updates
    - TimelineItem creation from completed tasks
    - Async playbook execution status polling
    """

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
        """
        Initialize TaskManager

        Args:
            tasks_store: TasksStore instance
            timeline_items_store: TimelineItemsStore instance
            plan_builder: PlanBuilder instance (for side_effect_level determination)
            playbook_runner: PlaybookRunner instance
            default_locale: Default locale for i18n
            artifacts_store: ArtifactsStore instance (optional, for artifact creation)
            store: MindscapeStore instance (optional, for creating MindEvents)
        """
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.plan_builder = plan_builder
        self.playbook_runner = playbook_runner
        self.i18n = get_i18n_service(default_locale=default_locale)
        self.artifacts_store = artifacts_store
        self.store = store
        self.artifact_extractor = ArtifactExtractor(store)

    async def create_timeline_item_from_task(
        self, task: Task, execution_result: Dict[str, Any], playbook_code: str
    ) -> Optional[TimelineItem]:
        """
        Create TimelineItem from completed task

        Args:
            task: Completed task
            execution_result: Execution result data
            playbook_code: Playbook code

        Returns:
            Created TimelineItem or None if creation failed
        """
        try:
            side_effect_level = self.plan_builder.determine_side_effect_level(
                playbook_code
            )
            timeline_item = create_task_completion_timeline_item(
                task=task,
                execution_result=execution_result,
                playbook_code=playbook_code,
                side_effect_level=side_effect_level,
                i18n=self.i18n,
                utc_now_fn=_utc_now,
            )

            self.timeline_items_store.create_timeline_item(timeline_item)
            logger.info(f"Created timeline item: {timeline_item.id} for task {task.id}")

            if self.artifacts_store:
                await attach_artifact_to_timeline_item(
                    store=self.store,
                    artifacts_store=self.artifacts_store,
                    timeline_items_store=self.timeline_items_store,
                    artifact_extractor=self.artifact_extractor,
                    task=task,
                    timeline_item=timeline_item,
                    execution_result=execution_result,
                    playbook_code=playbook_code,
                    get_next_version_fn=self.artifact_extractor._get_next_version,
                    update_latest_markers_fn=self._update_artifact_latest_markers,
                    create_mind_event_fn=self._create_artifact_mind_event,
                )

            # Update task status to succeeded
            self.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                result=execution_result,
                completed_at=_utc_now(),
            )

            # Create graph node for completed task (Task → Graph integration)
            await self._create_graph_node_for_task(
                task=task,
                timeline_item=timeline_item,
                playbook_code=playbook_code,
                execution_result=execution_result,
            )

            # Mark task as notification sent (for completion notification)
            self._mark_task_notification_sent(task.id)

            return timeline_item

        except Exception as e:
            logger.error(
                f"Failed to create TimelineItem from task {task.id}: {e}", exc_info=True
            )
            # Update task status to failed
            try:
                self.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error=str(e),
                    completed_at=_utc_now(),
                )
            except Exception as update_error:
                logger.error(f"Failed to update task status: {update_error}")
            return None

    def _mark_task_notification_sent(self, task_id: str) -> None:
        """
        Mark task as notification sent

        This creates a completion event that can be used for notifications.
        In the future, this could trigger WebSocket push or other notification mechanisms.

        Args:
            task_id: Task ID
        """
        try:
            self.tasks_store.update_task(task_id, notification_sent_at=_utc_now())
            logger.debug(f"Marked task {task_id} as notification sent")
        except Exception as e:
            logger.warning(f"Failed to mark task {task_id} as notification sent: {e}")

    async def _create_graph_node_for_task(
        self,
        task: Task,
        timeline_item: TimelineItem,
        playbook_code: str,
        execution_result: Dict[str, Any],
    ) -> None:
        """
        Update planned graph node to completed status (Task → Graph integration).

        This implements the "draw dashed line first" pattern:
        - Node was created with status="planned" when task started (by TaskCreator)
        - This method updates it to status="completed" and applies the change

        If no pending_graph_node_id exists (task created without graph node),
        falls back to creating a new node.

        Args:
            task: Completed Task object
            timeline_item: Created TimelineItem
            playbook_code: Playbook code that was executed
            execution_result: Execution result data
        """
        try:
            # Extract execution context for Intent/Lens binding
            execution_context = {}
            if hasattr(task, "execution_context") and task.execution_context:
                execution_context = task.execution_context
            elif hasattr(task, "metadata") and task.metadata:
                execution_context = task.metadata.get("execution_context", {})

            # Check if we have a pending graph node created by TaskCreator
            pending_graph_node_id = execution_context.get("pending_graph_node_id")

            graph_store = GraphChangelogStore()

            if pending_graph_node_id:
                # Update existing planned node to completed and apply
                try:
                    result = graph_store.apply_change(
                        change_id=pending_graph_node_id,
                        applied_by="system:task_completion",
                    )
                    if result.get("success"):
                        logger.info(
                            f"Applied graph node {pending_graph_node_id} for completed task {task.id}"
                        )
                        return
                    else:
                        logger.warning(
                            f"Failed to apply graph node {pending_graph_node_id}: {result.get('error')}"
                        )
                except Exception as e:
                    logger.warning(f"Error applying graph node: {e}")

            # Fallback: create new node if no pending node exists
            # Extract Intent binding (retrospective)
            origin_intent_id = execution_context.get("origin_intent_id")
            origin_intent_label = execution_context.get("origin_intent_label")
            intent_confidence = execution_context.get("intent_confidence")

            # Extract Lens binding (retrospective)
            lens_snapshot_hash = execution_context.get("effective_lens_hash")

            # Build node metadata with all bindings
            node_metadata = {
                "playbook_code": playbook_code,
                "timeline_item_id": timeline_item.id,
                "task_id": task.id,
                "message_id": task.message_id,
                # Intent binding (retrospective)
                "origin_intent_id": origin_intent_id,
                "origin_intent_label": origin_intent_label,
                "intent_confidence": intent_confidence,
                # Lens binding (retrospective)
                "lens_snapshot_hash": lens_snapshot_hash,
                # Execution metadata
                "completed_at": (
                    task.completed_at.isoformat()
                    if hasattr(task, "completed_at") and task.completed_at
                    else _utc_now().isoformat()
                ),
                "timeline_item_type": (
                    timeline_item.type.value
                    if hasattr(timeline_item.type, "value")
                    else str(timeline_item.type)
                ),
                # Artifact reference (if exists)
                "artifact_id": (
                    timeline_item.data.get("artifact_id")
                    if timeline_item.data
                    else None
                ),
            }

            # Create and auto-apply completed node (no pending node existed)
            change_id = graph_store.create_pending_change(
                workspace_id=task.workspace_id,
                operation="create_node",
                target_type="node",  # Must be: node, edge, overlay, or batch
                target_id=task.id,
                after_state={
                    "id": task.id,
                    "node_type": "task",  # Distinguishes from intent/lens nodes
                    "label": timeline_item.title or playbook_code,
                    "status": "completed",
                    "metadata": node_metadata,
                    "created_at": _utc_now().isoformat(),
                },
                actor="system",
                actor_context="task_completion",
            )

            # Auto-apply system-created nodes
            graph_store.apply_change(change_id, applied_by="system:auto_apply")

            logger.info(
                f"Created and applied graph node for task {task.id} "
                f"(intent: {origin_intent_id}, lens: {lens_snapshot_hash})"
            )

        except Exception as e:
            # Graph node creation is non-critical, don't fail the task
            logger.warning(
                f"Failed to handle graph node for task {task.id}: {e}",
                exc_info=True,
            )

    def mark_task_as_displayed(self, task_id: str) -> None:
        """
        Mark task as displayed (frontend has shown the completion notification)

        This allows frontend to hide the notification after 1-2 seconds.

        Args:
            task_id: Task ID
        """
        try:
            self.tasks_store.update_task(task_id, displayed_at=_utc_now())
            logger.debug(f"Marked task {task_id} as displayed")
        except Exception as e:
            logger.warning(f"Failed to mark task {task_id} as displayed: {e}")

    async def _create_artifact_mind_event(
        self, artifact, task: Task, execution_result: Dict[str, Any]
    ) -> None:
        await create_artifact_mind_event_helper(
            store=self.store,
            artifact=artifact,
            task=task,
            execution_result=execution_result,
            utc_now_fn=_utc_now,
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
        self, task: Task, execution_id: Optional[str], playbook_code: str
    ) -> None:
        """
        Check playbook execution status and update task/timeline accordingly

        For async executions, this method checks if execution is complete
        and updates task status and creates timeline item.

        Args:
            task: Task to check
            execution_id: Playbook execution ID
            playbook_code: Playbook code
        """
        try:
            if not execution_id:
                return

            # Check if task is already completed
            if task.status in [TaskStatus.SUCCEEDED, TaskStatus.FAILED]:
                return

            # Try to get execution result from playbook runner
            try:
                # Check if playbook_runner has get_playbook_execution_result method
                if hasattr(self.playbook_runner, "get_playbook_execution_result"):
                    try:
                        execution_result_data = (
                            await self.playbook_runner.get_playbook_execution_result(
                                execution_id
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to get execution result for {execution_id}: {e}, falling back to active executions check"
                        )
                        execution_result_data = None
                else:
                    # Fallback: check if execution is still active
                    logger.warning(
                        f"playbook_runner.get_playbook_execution_result not available, checking active executions"
                    )
                    execution_result_data = None

                # If no result from get_playbook_execution_result, try fallback methods
                if execution_result_data is None:
                    # Check if execution is still active
                    if hasattr(self.playbook_runner, "list_active_executions"):
                        try:
                            active_executions = (
                                self.playbook_runner.list_active_executions()
                            )
                            if execution_id not in active_executions:
                                # Execution is no longer active but no result method
                                # Try to get result from task.result if it was already set (e.g., by playbook runner callback)
                                if task.result:
                                    # Task result already available, use it
                                    execution_result_data = (
                                        task.result
                                        if isinstance(task.result, dict)
                                        else {
                                            "result": task.result,
                                            "status": "completed",
                                        }
                                    )
                                    logger.info(
                                        f"Using task.result for completed execution {execution_id}"
                                    )
                                else:
                                    # No result available - mark as completed with unknown result
                                    # This creates a TimelineItem so user can see the execution completed
                                    execution_result_data = {
                                        "status": "completed",
                                        "note": "Execution completed but result retrieval not available",
                                    }
                                    logger.warning(
                                        f"Execution {execution_id} completed but no result available, creating placeholder TimelineItem"
                                    )
                            else:
                                # Still running
                                execution_result_data = None
                        except Exception as e:
                            logger.warning(
                                f"Failed to check active executions: {e}, task {task.id} remains RUNNING"
                            )
                            execution_result_data = None
                    else:
                        # No list_active_executions method available
                        logger.warning(
                            f"playbook_runner.list_active_executions not available, cannot determine execution status for {execution_id}"
                        )
                        # Check if task.result is available as last resort
                        if task.result:
                            execution_result_data = (
                                task.result
                                if isinstance(task.result, dict)
                                else {"result": task.result, "status": "completed"}
                            )
                            logger.info(
                                f"Using task.result as fallback for execution {execution_id}"
                            )
                        else:
                            # Cannot determine status, task remains RUNNING
                            logger.warning(
                                f"Cannot determine execution status for {execution_id}, task {task.id} remains RUNNING"
                            )
                            execution_result_data = None

                if execution_result_data:
                    # Execution is complete, update task and create timeline item
                    # Update task status first
                    self.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.SUCCEEDED,
                        result=execution_result_data,
                        completed_at=_utc_now(),
                    )

                    # Create timeline item
                    timeline_item = await self.create_timeline_item_from_task(
                        task=task,
                        execution_result=execution_result_data,
                        playbook_code=playbook_code,
                    )

                    if timeline_item:
                        logger.info(
                            f"Updated task {task.id} from async execution {execution_id}, created timeline item {timeline_item.id}"
                        )

                        # Mark task as notification sent (for completion notification)
                        self._mark_task_notification_sent(task.id)
                    else:
                        logger.warning(
                            f"Failed to create timeline item for task {task.id}"
                        )
                else:
                    # Check if execution is still active in playbook runner
                    active_executions = (
                        self.playbook_runner.list_active_executions()
                        if hasattr(self.playbook_runner, "list_active_executions")
                        else []
                    )
                    if execution_id not in active_executions:
                        # Execution is no longer active but no result - mark as failed
                        self.tasks_store.update_task_status(
                            task_id=task.id,
                            status=TaskStatus.FAILED,
                            error="Execution completed but no result available",
                            completed_at=_utc_now(),
                        )

                        # Create error TimelineItem for failed execution
                        error_timeline_item = create_failed_execution_timeline_item(
                            task=task,
                            playbook_code=playbook_code,
                            error_message="Execution completed but no result available",
                            utc_now_fn=_utc_now,
                        )
                        self.timeline_items_store.create_timeline_item(
                            error_timeline_item
                        )

                        logger.warning(
                            f"Task {task.id} execution {execution_id} no longer active, marked as failed, created error timeline item"
                        )
                    else:
                        # Execution still in progress, task remains RUNNING
                        logger.debug(
                            f"Task {task.id} execution {execution_id} still in progress"
                        )
            except Exception as e:
                logger.warning(
                    f"Failed to check execution status for task {task.id}: {e}"
                )
                # Task remains RUNNING, will be checked on next poll

        except Exception as e:
            logger.error(f"Failed to check and update task status: {e}", exc_info=True)

    def check_and_timeout_tasks(
        self, timeout_minutes: int = TASK_TIMEOUT_MINUTES
    ) -> List[str]:
        """
        Check for tasks that have been running too long and mark them as failed

        This method should be called periodically (e.g., on API requests or via background task)
        to detect and handle stuck tasks.

        Args:
            timeout_minutes: Maximum time a task can run before being considered timed out

        Returns:
            List of task IDs that were timed out
        """
        timed_out_task_ids = []
        try:
            # Get all RUNNING tasks
            running_tasks = self.tasks_store.list_tasks_by_workspace(
                workspace_id=None,  # Get all workspaces
                status=TaskStatus.RUNNING,
                limit=1000,  # Large limit to check all running tasks
            )

            if not running_tasks:
                return timed_out_task_ids

            timeout_threshold = _utc_now() - timedelta(minutes=timeout_minutes)

            for task in running_tasks:
                # Check if task has been running too long
                # Use started_at if available, otherwise use created_at
                start_time = task.started_at or task.created_at
                if start_time:
                    # Ensure both times are timezone-naive for comparison
                    # start_time from database is already timezone-naive (UTC)
                    # timeout_threshold is also timezone-naive (UTC from _utc_now())
                    if start_time < timeout_threshold:
                        # Task has timed out
                        try:
                            # Gather diagnostic information
                            execution_context = task.execution_context or {}
                            execution_id = task.execution_id or task.id

                            # Try to get execution steps for diagnosis
                            diagnostic_info = {
                                "pack_id": task.pack_id,
                                "execution_id": execution_id,
                                "started_at": start_time.isoformat(),
                                "timeout_after_minutes": timeout_minutes,
                                "current_time": _utc_now().isoformat(),
                            }

                            # Check if there are any execution steps
                            try:
                                from ...services.mindscape_store import MindscapeStore

                                store = MindscapeStore()
                                from ...models.mindscape import EventType

                                # Get playbook step events
                                events = store.get_events_by_workspace(
                                    workspace_id=task.workspace_id, limit=100
                                )
                                step_events = [
                                    e
                                    for e in events
                                    if e.event_type == EventType.PLAYBOOK_STEP
                                    and execution_id in (e.entity_ids or [])
                                ]

                                if step_events:
                                    diagnostic_info["steps_found"] = len(step_events)
                                    # Get last step info
                                    last_step = max(
                                        step_events, key=lambda e: e.timestamp
                                    )
                                    last_step_payload = (
                                        last_step.payload
                                        if isinstance(last_step.payload, dict)
                                        else {}
                                    )
                                    diagnostic_info["last_step"] = {
                                        "step_name": last_step_payload.get(
                                            "step_name", "unknown"
                                        ),
                                        "status": last_step_payload.get(
                                            "status", "unknown"
                                        ),
                                        "timestamp": (
                                            last_step.timestamp.isoformat()
                                            if hasattr(last_step.timestamp, "isoformat")
                                            else str(last_step.timestamp)
                                        ),
                                    }
                                else:
                                    diagnostic_info["steps_found"] = 0
                                    diagnostic_info["diagnosis"] = (
                                        "No execution steps found - playbook may not have started or is stuck at initialization"
                                    )
                            except Exception as diag_error:
                                logger.warning(
                                    f"Failed to gather diagnostic info for timed out task {task.id}: {diag_error}"
                                )
                                diagnostic_info["diagnosis_error"] = str(diag_error)

                            timeout_error = (
                                f"Task timed out after {timeout_minutes} minutes. "
                                f"Started at {start_time.isoformat()}. "
                                f"Diagnosis: {diagnostic_info.get('diagnosis', 'Unknown - check execution steps')}"
                            )

                            logger.warning(
                                f"Task {task.id} (pack: {task.pack_id}, execution: {execution_id}) timed out. "
                                f"Diagnostic info: {diagnostic_info}"
                            )

                            # Update execution_context with failure information
                            execution_context["failure_type"] = "timeout"
                            execution_context["failure_reason"] = timeout_error
                            execution_context["timeout_diagnostic"] = diagnostic_info

                            # Update task status to FAILED
                            self.tasks_store.update_task_status(
                                task_id=task.id,
                                status=TaskStatus.FAILED,
                                error=timeout_error,
                                completed_at=_utc_now(),
                            )

                            # Update execution_context
                            self.tasks_store.update_task(
                                task.id, execution_context=execution_context
                            )

                            # Create error TimelineItem for timed out task
                            error_timeline_item = create_timeout_timeline_item(
                                task=task,
                                timeout_error=timeout_error,
                                timeout_minutes=timeout_minutes,
                                i18n=self.i18n,
                                utc_now_fn=_utc_now,
                            )
                            self.timeline_items_store.create_timeline_item(
                                error_timeline_item
                            )

                            timed_out_task_ids.append(task.id)
                            logger.info(
                                f"Task {task.id} marked as timed out and failed"
                            )

                        except Exception as e:
                            logger.error(
                                f"Failed to mark task {task.id} as timed out: {e}",
                                exc_info=True,
                            )

        except Exception as e:
            logger.error(f"Failed to check for timed out tasks: {e}", exc_info=True)

        return timed_out_task_ids
