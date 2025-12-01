"""
Task Manager

Manages Task and TimelineItem lifecycle: creation, status updates, and polling.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import uuid

from ...models.workspace import Task, TaskStatus, TimelineItem, TimelineItemType, SideEffectLevel
from ...services.stores.tasks_store import TasksStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...services.stores.artifacts_store import ArtifactsStore
from ...services.i18n_service import get_i18n_service
from .artifact_extractor import ArtifactExtractor

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

    def __init__(self, tasks_store: TasksStore, timeline_items_store: TimelineItemsStore,
                 plan_builder, playbook_runner, default_locale: str = "en", artifacts_store: ArtifactsStore = None,
                 store=None):
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

    def create_timeline_item_from_task(
        self,
        task: Task,
        execution_result: Dict[str, Any],
        playbook_code: str
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
            # Determine timeline item type based on playbook code and execution result
            item_type = TimelineItemType.PLAN
            playbook_lower = playbook_code.lower()

            # Check for error first
            if execution_result.get("error") or "error" in playbook_lower:
                item_type = TimelineItemType.ERROR
            # Check for specific pack types
            elif "semantic_seeds" in playbook_lower or "intent" in playbook_lower or "seed" in playbook_lower:
                item_type = TimelineItemType.INTENT_SEEDS
            elif "draft" in playbook_lower or "content_drafting" in playbook_lower:
                item_type = TimelineItemType.DRAFT
            elif "summary" in playbook_lower or "summarize" in playbook_lower:
                item_type = TimelineItemType.SUMMARY
            # Check execution_result for type hints
            elif execution_result.get("type"):
                try:
                    item_type = TimelineItemType(execution_result.get("type"))
                except (ValueError, TypeError):
                    pass

            # Extract title and summary from execution result
            title = execution_result.get("title") or playbook_code
            summary = execution_result.get("summary") or execution_result.get("message") or f"Completed {playbook_code}"

            # Determine side effect level for CTA generation
            side_effect_level = self.plan_builder.determine_side_effect_level(playbook_code)
            cta = None

            # Determine CTA label based on task type
            playbook_lower = playbook_code.lower()
            view_result_label = "View Result"  # Default label

            # Customize label based on task type
            if "draft" in playbook_lower or "content" in playbook_lower or "writing" in playbook_lower:
                view_result_label = "View File"
            elif "plan" in playbook_lower or "planning" in playbook_lower:
                view_result_label = "View Plan"
            elif "summary" in playbook_lower or "summarize" in playbook_lower:
                view_result_label = "View Summary"
            elif "intent" in playbook_lower or "seed" in playbook_lower:
                view_result_label = "View Intent"
            elif "task" in playbook_lower:
                view_result_label = "View Task"

            if side_effect_level == SideEffectLevel.SOFT_WRITE:
                # Generate CTA for soft_write actions
                # Determine action type based on playbook_code or execution_result
                action_type = execution_result.get("action_type") or "add_to_intents"
                if "intent" in playbook_code.lower() or "seed" in playbook_code.lower():
                    action_type = "add_to_intents"
                elif "task" in playbook_code.lower() or "plan" in playbook_code.lower():
                    action_type = "add_to_tasks"
                else:
                    action_type = "add_to_intents"  # Default

                cta = [{
                    "label": self.i18n.t("conversation_orchestrator", "suggestion.cta_add"),
                    "action": action_type
                }, {
                    "label": view_result_label,
                    "action": "view_result"
                }]
            elif side_effect_level == SideEffectLevel.EXTERNAL_WRITE:
                # Generate CTA for external_write actions (requires confirmation)
                # Determine action type from playbook_code or execution_result
                action_type = execution_result.get("action_type") or "publish_to_wordpress"
                if "wordpress" in playbook_code.lower() or "wp" in playbook_code.lower():
                    action_type = "publish_to_wordpress"
                elif "export" in playbook_code.lower():
                    action_type = "export_document"
                else:
                    action_type = "execute_external_action"

                cta = [{
                    "label": self.i18n.t("conversation_orchestrator", "confirmation.button_confirm"),
                    "action": action_type,
                    "requires_confirm": True
                }, {
                    "label": view_result_label,
                    "action": "view_result"
                }]
            else:
                # For READONLY tasks, add view_result CTA
                cta = [{
                    "label": view_result_label,
                    "action": "view_result"
                }]

            # Create TimelineItem
            timeline_item = TimelineItem(
                id=str(uuid.uuid4()),
                workspace_id=task.workspace_id,
                message_id=task.message_id,
                task_id=task.id,
                type=item_type,
                title=title,
                summary=summary,
                data=execution_result,
                cta=cta,
                created_at=datetime.utcnow()
            )

            self.timeline_items_store.create_timeline_item(timeline_item)
            logger.info(f"Created timeline item: {timeline_item.id} for task {task.id}")

            # Extract and create artifact if applicable
            artifact = None
            artifact_warning = None
            if self.artifacts_store:
                try:
                    # Pre-execution safety check: verify workspace storage_base_path is configured and writable
                    workspace = self.store.workspaces.get_workspace(task.workspace_id)
                    if not workspace:
                        artifact_warning = {
                            "type": "workspace_not_found",
                            "message": "Workspace not found, artifact creation skipped",
                            "action_required": "Please check workspace configuration"
                        }
                        logger.warning(f"Workspace {task.workspace_id} not found, skipping artifact creation")
                    elif not workspace.storage_base_path:
                        artifact_warning = {
                            "type": "storage_path_not_configured",
                            "message": "Workspace storage path not configured. Artifact creation skipped.",
                            "action_required": "Please set storage path in workspace settings",
                            "storage_path_missing": True
                        }
                        logger.warning(
                            f"Workspace {task.workspace_id} has no storage_base_path configured. "
                            "Artifact creation will be skipped. Please set storage path in workspace settings."
                        )
                    else:
                        # Check if path exists and is writable
                        storage_path = Path(workspace.storage_base_path).expanduser().resolve()
                        if not storage_path.exists():
                            # Try to create the directory automatically
                            try:
                                storage_path.mkdir(parents=True, exist_ok=True)
                                logger.info(f"Created storage directory: {storage_path}")
                            except Exception as e:
                                artifact_warning = {
                                    "type": "storage_path_not_exists",
                                    "message": f"Storage path does not exist and cannot be created: {storage_path}",
                                    "action_required": f"Please check workspace storage configuration or create the directory: {str(e)}",
                                    "storage_path": str(storage_path)
                                }
                                logger.warning(
                                    f"Storage path does not exist and creation failed: {storage_path}. Error: {e}"
                                )
                        elif not os.access(storage_path, os.W_OK):
                            artifact_warning = {
                                "type": "storage_path_not_writable",
                                "message": f"Storage path is not writable: {storage_path}",
                                "action_required": "Please check directory permissions",
                                "storage_path": str(storage_path)
                            }
                            logger.warning(
                                f"Storage path is not writable: {storage_path}. "
                                "Artifact creation will be skipped. Please check directory permissions."
                            )
                        else:
                            # Path validation passed, proceed with artifact extraction
                            # Extract intent_id from execution_result or task
                            intent_id = execution_result.get("intent_id")
                            if not intent_id and hasattr(task, 'intent_id'):
                                intent_id = task.intent_id
                            if not intent_id and hasattr(task, 'metadata') and isinstance(task.metadata, dict):
                                intent_id = task.metadata.get("intent_id")

                            # Extract artifact from execution result
                            artifact = self.artifact_extractor.extract_artifact_from_task_result(
                                task=task,
                                execution_result=execution_result,
                                playbook_code=playbook_code,
                                intent_id=intent_id
                            )

                            # Check if artifact extraction succeeded but file write failed (handled in extractor)
                            if artifact and hasattr(artifact, 'metadata') and artifact.metadata:
                                if artifact.metadata.get('write_failed'):
                                    artifact_warning = {
                                        "type": "artifact_write_failed",
                                        "message": artifact.metadata.get('write_error', 'Failed to write artifact file'),
                                        "action_required": "Artifact content is available but file write failed. Please check storage configuration.",
                                        "fallback_path": artifact.storage_ref
                                    }

                    if artifact:
                        # Get version number for this artifact
                        version = self.artifact_extractor._get_next_version(
                            workspace_id=task.workspace_id,
                            playbook_code=playbook_code,
                            artifact_type=artifact.artifact_type.value
                        )

                        # Set version and is_latest in metadata
                        if artifact.metadata is None:
                            artifact.metadata = {}
                        artifact.metadata['version'] = version
                        artifact.metadata['is_latest'] = True  # Will be updated after creation

                        # Set sync state if cloud sync is enabled
                        # sync_state: None (disabled) | "pending" (pending sync) | "synced" (synced) | "failed" (sync failed)
                        if artifact.sync_state is None:
                            try:
                                storage_config = workspace.storage_config or {}
                                if isinstance(storage_config, str):
                                    import json
                                    storage_config = json.loads(storage_config)

                                cloud_enabled = storage_config.get("cloud_enabled", False)
                                if not cloud_enabled:
                                    cloud_enabled = os.getenv("CLOUD_SYNC_ENABLED", "false").lower() == "true"

                                if cloud_enabled:
                                    artifact.sync_state = "pending"
                                    logger.info(f"Artifact {artifact.id} marked as pending sync")
                            except Exception as e:
                                logger.warning(f"Failed to check cloud sync configuration: {e}, defaulting to None")
                                artifact.sync_state = None

                        # Create artifact record
                        artifact = self.artifacts_store.create_artifact(artifact)
                        logger.info(f"Created artifact: {artifact.id} for task {task.id}")

                        # Update is_latest markers
                        self._update_artifact_latest_markers(
                            workspace_id=task.workspace_id,
                            playbook_code=playbook_code,
                            artifact_type=artifact.artifact_type.value,
                            new_artifact_id=artifact.id
                        )

                        # Add artifact_id to timeline_item.data
                        if timeline_item.data:
                            timeline_item.data['artifact_id'] = artifact.id
                        else:
                            timeline_item.data = {'artifact_id': artifact.id}

                        # Update timeline item with artifact_id
                        self.timeline_items_store.update_timeline_item(
                            item_id=timeline_item.id,
                            data=timeline_item.data
                        )

                        # Create MindEvent for artifact (for embedding and external sync)
                        self._create_artifact_mind_event(artifact, task, execution_result)

                    # Record warning in TimelineItem if artifact creation failed
                    if artifact_warning:
                        # Update TimelineItem data with artifact_warning
                        if not timeline_item.data:
                            timeline_item.data = {}
                        timeline_item.data['artifact_warning'] = artifact_warning
                        timeline_item.data['artifact_creation_failed'] = True

                        # Update TimelineItem to persist warning information
                        self.timeline_items_store.update_timeline_item(
                            item_id=timeline_item.id,
                            data=timeline_item.data
                        )

                        logger.warning(
                            f"Artifact creation failed for task {task.id}: {artifact_warning.get('message')}. "
                            f"Warning recorded in timeline item {timeline_item.id}."
                        )
                except Exception as e:
                    logger.error(f"Error during artifact creation for task {task.id}: {e}", exc_info=True)
                    # Record error in timeline_item
                    if not timeline_item.data:
                        timeline_item.data = {}
                    timeline_item.data['artifact_warning'] = {
                        "type": "artifact_creation_error",
                        "message": f"Unexpected error during artifact creation: {str(e)}",
                        "action_required": "Please check logs and try again"
                    }
                    timeline_item.data['artifact_creation_failed'] = True
                    self.timeline_items_store.update_timeline_item(
                        item_id=timeline_item.id,
                        data=timeline_item.data
                    )

                except Exception as e:
                    logger.warning(f"Failed to create artifact for task {task.id}: {e}", exc_info=True)

            # Update task status to succeeded
            self.tasks_store.update_task_status(
                task_id=task.id,
                status=TaskStatus.SUCCEEDED,
                result=execution_result,
                completed_at=datetime.utcnow()
            )

            # Mark task as notification sent (for completion notification)
            self._mark_task_notification_sent(task.id)

            return timeline_item

        except Exception as e:
            logger.error(f"Failed to create TimelineItem from task {task.id}: {e}", exc_info=True)
            # Update task status to failed
            try:
                self.tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error=str(e),
                    completed_at=datetime.utcnow()
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
            import sqlite3
            import os

            db_path = self.tasks_store.db_path
            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        'UPDATE tasks SET notification_sent_at = ? WHERE id = ?',
                        (datetime.utcnow().isoformat(), task_id)
                    )
                    conn.commit()
                    logger.debug(f"Marked task {task_id} as notification sent")
                finally:
                    conn.close()
        except Exception as e:
            logger.warning(f"Failed to mark task {task_id} as notification sent: {e}")

    def mark_task_as_displayed(self, task_id: str) -> None:
        """
        Mark task as displayed (frontend has shown the completion notification)

        This allows frontend to hide the notification after 1-2 seconds.

        Args:
            task_id: Task ID
        """
        try:
            import sqlite3
            import os

            db_path = self.tasks_store.db_path
            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        'UPDATE tasks SET displayed_at = ? WHERE id = ?',
                        (datetime.utcnow().isoformat(), task_id)
                    )
                    conn.commit()
                    logger.debug(f"Marked task {task_id} as displayed")
                finally:
                    conn.close()
        except Exception as e:
            logger.warning(f"Failed to mark task {task_id} as displayed: {e}")

    def _create_artifact_mind_event(
        self,
        artifact,
        task: Task,
        execution_result: Dict[str, Any]
    ) -> None:
        """
        Create MindEvent for artifact (for embedding and external sync)

        Args:
            artifact: Created Artifact object
            task: Task object
            execution_result: Execution result dict
        """
        if not self.store:
            logger.debug("Store not available, skipping MindEvent creation for artifact")
            return

        try:
            from ...models.mindscape import MindEvent, EventType, EventActor

            # Get workspace to get owner_user_id
            workspace = self.store.get_workspace(task.workspace_id)
            if not workspace:
                logger.warning(f"Workspace {task.workspace_id} not found, cannot create MindEvent for artifact")
                return

            # Build entity_ids (include artifact_id and intent_id)
            entity_ids = [artifact.id]
            if artifact.intent_id:
                entity_ids.append(artifact.intent_id)

            # Create MindEvent
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                actor=EventActor.SYSTEM,
                channel="workspace",
                profile_id=workspace.owner_user_id,
                workspace_id=task.workspace_id,
                event_type=EventType.PLAYBOOK_STEP,
                payload={
                    "action": "artifact_created",
                    "artifact_id": artifact.id,
                    "playbook_code": artifact.playbook_code,
                    "task_id": task.id,
                    "intent_id": artifact.intent_id
                },
                entity_ids=entity_ids,
                metadata={
                    "is_artifact": True,
                    "artifact_type": artifact.artifact_type.value
                }
            )

            # Write to events store
            self.store.events.create_event(event, generate_embedding=True)
            logger.info(f"Created MindEvent for artifact {artifact.id}")

        except Exception as e:
            logger.warning(f"Failed to create MindEvent for artifact: {e}", exc_info=True)

    def retry_artifact_creation(
        self,
        timeline_item_id: str
    ) -> Dict[str, Any]:
        """
        Retry creating artifact (from timeline_item)

        Retrieves task and execution_result from timeline_item, then retries creating artifact.
        If successful, updates timeline_item to remove warning message.

        Args:
            timeline_item_id: Timeline item ID

        Returns:
            Dict with success status and artifact_id (if successful) or error message
        """
        try:
            # Get timeline_item
            timeline_item = self.timeline_items_store.get_timeline_item(timeline_item_id)
            if not timeline_item:
                return {"success": False, "error": "Timeline item not found"}

            # Check if artifact_creation_failed flag exists
            if not (timeline_item.data and timeline_item.data.get('artifact_creation_failed')):
                return {"success": False, "error": "No artifact creation failure recorded for this timeline item"}

            # Get task
            if not timeline_item.task_id:
                return {"success": False, "error": "Timeline item has no associated task"}

            task = self.tasks_store.get_task(timeline_item.task_id)
            if not task:
                return {"success": False, "error": "Task not found"}

            # Get execution_result (from timeline_item.data or task.result)
            execution_result = timeline_item.data.copy() if timeline_item.data else {}
            if not execution_result and task.result:
                execution_result = task.result

            if not execution_result:
                return {"success": False, "error": "No execution result available for artifact creation"}

            # Get playbook_code (from task.pack_id or execution_result)
            playbook_code = execution_result.get("playbook_code") or task.pack_id or "unknown"

            # Check workspace storage configuration
            workspace = self.store.workspaces.get_workspace(timeline_item.workspace_id)
            if not workspace:
                return {"success": False, "error": "Workspace not found"}

            if not workspace.storage_base_path:
                return {
                    "success": False,
                    "error": "Workspace storage path not configured",
                    "action_required": "Please set storage path in workspace settings"
                }

            # Check if path exists and is writable
            storage_path = Path(workspace.storage_base_path).expanduser().resolve()
            if not storage_path.exists():
                try:
                    storage_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Created storage directory for retry: {storage_path}")
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to create storage path {storage_path}: {str(e)}",
                        "action_required": "Please check workspace storage configuration or create the directory"
                    }

            if not os.access(storage_path, os.W_OK):
                return {
                    "success": False,
                    "error": f"Storage path is not writable: {storage_path}",
                    "action_required": "Please check directory permissions"
                }

            # Extract intent_id
            intent_id = execution_result.get("intent_id")
            if not intent_id and hasattr(task, 'intent_id'):
                intent_id = task.intent_id
            if not intent_id and hasattr(task, 'metadata') and isinstance(task.metadata, dict):
                intent_id = task.metadata.get("intent_id")

            # Re-extract artifact
            try:
                artifact = self.artifact_extractor.extract_artifact_from_task_result(
                    task=task,
                    execution_result=execution_result,
                    playbook_code=playbook_code,
                    intent_id=intent_id
                )
            except Exception as e:
                logger.error(f"Error extracting artifact during retry: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Failed to extract artifact: {str(e)}",
                    "action_required": "Please check execution result format and try again"
                }

            if not artifact:
                logger.warning(
                    f"extract_artifact_from_task_result returned None for task {task.id}, "
                    f"playbook_code: {playbook_code}, execution_result keys: {list(execution_result.keys()) if execution_result else 'None'}"
                )
                return {
                    "success": False,
                    "error": "Failed to extract artifact from execution result. The execution result may not contain artifact data.",
                    "action_required": "Please check if the task execution completed successfully"
                }

            # Check if file write failed
            if artifact.metadata and artifact.metadata.get('write_failed'):
                return {
                    "success": False,
                    "error": artifact.metadata.get('write_error', 'Failed to write artifact file'),
                    "action_required": "Artifact content is available but file write failed. Please check storage configuration."
                }

            # Get version number
            version = self.artifact_extractor._get_next_version(
                workspace_id=timeline_item.workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact.artifact_type.value
            )

            # Set version and is_latest
            if artifact.metadata is None:
                artifact.metadata = {}
            artifact.metadata['version'] = version
            artifact.metadata['is_latest'] = True

            # Create artifact record
            artifact = self.artifacts_store.create_artifact(artifact)
            logger.info(f"Retry created artifact: {artifact.id} for timeline item {timeline_item_id}")

            # Update is_latest marker
            self._update_artifact_latest_markers(
                workspace_id=timeline_item.workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact.artifact_type.value,
                new_artifact_id=artifact.id
            )

            # Update timeline_item, remove warning info, add artifact_id
            if not timeline_item.data:
                timeline_item.data = {}
            timeline_item.data['artifact_id'] = artifact.id
            timeline_item.data.pop('artifact_warning', None)
            timeline_item.data.pop('artifact_creation_failed', None)

            self.timeline_items_store.update_timeline_item(
                item_id=timeline_item.id,
                data=timeline_item.data
            )

            # Create MindEvent
            self._create_artifact_mind_event(artifact, task, execution_result)

            return {
                "success": True,
                "artifact_id": artifact.id,
                "message": "Artifact created successfully"
            }

        except Exception as e:
            logger.error(f"Failed to retry artifact creation for timeline item {timeline_item_id}: {e}", exc_info=True)
            return {"success": False, "error": f"Unexpected error: {str(e)}"}

    def _update_artifact_latest_markers(
        self,
        workspace_id: str,
        playbook_code: str,
        artifact_type: str,
        new_artifact_id: str
    ) -> None:
        """
        Update artifact is_latest marker

        Set is_latest to False for other artifacts with same playbook and artifact_type,
        and ensure new artifact's is_latest is True.

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            artifact_type: Artifact type
            new_artifact_id: Newly created artifact ID
        """
        try:
            # Get all artifacts with same playbook
            artifacts = self.artifacts_store.list_artifacts_by_playbook(
                workspace_id, playbook_code
            )

            # Filter artifacts with same artifact_type (exclude new artifact)
            same_type_artifacts = [
                a for a in artifacts
                if (a.artifact_type.value == artifact_type or str(a.artifact_type) == artifact_type)
                and a.id != new_artifact_id
            ]

            # Set old versions' is_latest to False
            for old_artifact in same_type_artifacts:
                old_metadata = old_artifact.metadata or {}
                if old_metadata.get("is_latest", False):
                    updated_metadata = {**old_metadata, "is_latest": False}
                    self.artifacts_store.update_artifact(
                        old_artifact.id,
                        metadata=updated_metadata
                    )
                    logger.debug(
                        f"Updated artifact {old_artifact.id} is_latest to False "
                        f"(new artifact: {new_artifact_id})"
                    )

            # Ensure new artifact's is_latest is True
            new_artifact = self.artifacts_store.get_artifact(new_artifact_id)
            if new_artifact:
                new_metadata = new_artifact.metadata or {}
                if not new_metadata.get("is_latest", True):
                    updated_metadata = {**new_metadata, "is_latest": True}
                    self.artifacts_store.update_artifact(
                        new_artifact_id,
                        metadata=updated_metadata
                    )
                    logger.debug(f"Updated artifact {new_artifact_id} is_latest to True")

        except Exception as e:
            logger.warning(
                f"Failed to update artifact latest markers for {new_artifact_id}: {e}",
                exc_info=True
            )

    async def check_and_update_task_status(
        self,
        task: Task,
        execution_id: Optional[str],
        playbook_code: str
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
                if hasattr(self.playbook_runner, 'get_playbook_execution_result'):
                    try:
                        execution_result_data = await self.playbook_runner.get_playbook_execution_result(execution_id)
                    except Exception as e:
                        logger.warning(f"Failed to get execution result for {execution_id}: {e}, falling back to active executions check")
                        execution_result_data = None
                else:
                    # Fallback: check if execution is still active
                    logger.warning(f"playbook_runner.get_playbook_execution_result not available, checking active executions")
                    execution_result_data = None

                # If no result from get_playbook_execution_result, try fallback methods
                if execution_result_data is None:
                    # Check if execution is still active
                    if hasattr(self.playbook_runner, 'list_active_executions'):
                        try:
                            active_executions = self.playbook_runner.list_active_executions()
                            if execution_id not in active_executions:
                                # Execution is no longer active but no result method
                                # Try to get result from task.result if it was already set (e.g., by playbook runner callback)
                                if task.result:
                                    # Task result already available, use it
                                    execution_result_data = task.result if isinstance(task.result, dict) else {"result": task.result, "status": "completed"}
                                    logger.info(f"Using task.result for completed execution {execution_id}")
                                else:
                                    # No result available - mark as completed with unknown result
                                    # This creates a TimelineItem so user can see the execution completed
                                    execution_result_data = {"status": "completed", "note": "Execution completed but result retrieval not available"}
                                    logger.warning(f"Execution {execution_id} completed but no result available, creating placeholder TimelineItem")
                            else:
                                # Still running
                                execution_result_data = None
                        except Exception as e:
                            logger.warning(f"Failed to check active executions: {e}, task {task.id} remains RUNNING")
                            execution_result_data = None
                    else:
                        # No list_active_executions method available
                        logger.warning(f"playbook_runner.list_active_executions not available, cannot determine execution status for {execution_id}")
                        # Check if task.result is available as last resort
                        if task.result:
                            execution_result_data = task.result if isinstance(task.result, dict) else {"result": task.result, "status": "completed"}
                            logger.info(f"Using task.result as fallback for execution {execution_id}")
                        else:
                            # Cannot determine status, task remains RUNNING
                            logger.warning(f"Cannot determine execution status for {execution_id}, task {task.id} remains RUNNING")
                            execution_result_data = None

                if execution_result_data:
                    # Execution is complete, update task and create timeline item
                    # Update task status first
                    self.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.SUCCEEDED,
                        result=execution_result_data,
                        completed_at=datetime.utcnow()
                    )

                    # Create timeline item
                    timeline_item = self.create_timeline_item_from_task(
                        task=task,
                        execution_result=execution_result_data,
                        playbook_code=playbook_code
                    )

                    if timeline_item:
                        logger.info(f"Updated task {task.id} from async execution {execution_id}, created timeline item {timeline_item.id}")

                        # Mark task as notification sent (for completion notification)
                        self._mark_task_notification_sent(task.id)
                    else:
                        logger.warning(f"Failed to create timeline item for task {task.id}")
                else:
                    # Check if execution is still active in playbook runner
                    active_executions = self.playbook_runner.list_active_executions() if hasattr(self.playbook_runner, 'list_active_executions') else []
                    if execution_id not in active_executions:
                        # Execution is no longer active but no result - mark as failed
                        self.tasks_store.update_task_status(
                            task_id=task.id,
                            status=TaskStatus.FAILED,
                            error="Execution completed but no result available",
                            completed_at=datetime.utcnow()
                        )

                        # Create error TimelineItem for failed execution
                        error_timeline_item = TimelineItem(
                            id=str(uuid.uuid4()),
                            workspace_id=task.workspace_id,
                            message_id=task.message_id,
                            task_id=task.id,
                            type=TimelineItemType.ERROR,
                            title=f"Failed: {playbook_code}",
                            summary="Execution completed but no result available",
                            data={
                                "playbook_code": playbook_code,
                                "error": "Execution completed but no result available"
                            },
                            cta=None,
                            created_at=datetime.utcnow()
                        )
                        self.timeline_items_store.create_timeline_item(error_timeline_item)

                        logger.warning(f"Task {task.id} execution {execution_id} no longer active, marked as failed, created error timeline item")
                    else:
                        # Execution still in progress, task remains RUNNING
                        logger.debug(f"Task {task.id} execution {execution_id} still in progress")
            except Exception as e:
                logger.warning(f"Failed to check execution status for task {task.id}: {e}")
                # Task remains RUNNING, will be checked on next poll

        except Exception as e:
            logger.error(f"Failed to check and update task status: {e}", exc_info=True)

    def check_and_timeout_tasks(self, timeout_minutes: int = TASK_TIMEOUT_MINUTES) -> List[str]:
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
                limit=1000  # Large limit to check all running tasks
            )

            if not running_tasks:
                return timed_out_task_ids

            timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)

            for task in running_tasks:
                # Check if task has been running too long
                # Use started_at if available, otherwise use created_at
                start_time = task.started_at or task.created_at
                if start_time:
                    # Ensure both times are timezone-naive for comparison
                    # start_time from database is already timezone-naive (UTC)
                    # timeout_threshold is also timezone-naive (UTC from datetime.utcnow())
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
                                "current_time": datetime.utcnow().isoformat()
                            }

                            # Check if there are any execution steps
                            try:
                                from ...services.mindscape_store import MindscapeStore
                                store = MindscapeStore()
                                from ...models.mindscape import EventType

                                # Get playbook step events
                                events = store.get_events_by_workspace(
                                    workspace_id=task.workspace_id,
                                    limit=100
                                )
                                step_events = [
                                    e for e in events
                                    if e.event_type == EventType.PLAYBOOK_STEP
                                    and execution_id in (e.entity_ids or [])
                                ]

                                if step_events:
                                    diagnostic_info["steps_found"] = len(step_events)
                                    # Get last step info
                                    last_step = max(step_events, key=lambda e: e.timestamp)
                                    last_step_payload = last_step.payload if isinstance(last_step.payload, dict) else {}
                                    diagnostic_info["last_step"] = {
                                        "step_name": last_step_payload.get("step_name", "unknown"),
                                        "status": last_step_payload.get("status", "unknown"),
                                        "timestamp": last_step.timestamp.isoformat() if hasattr(last_step.timestamp, 'isoformat') else str(last_step.timestamp)
                                    }
                                else:
                                    diagnostic_info["steps_found"] = 0
                                    diagnostic_info["diagnosis"] = "No execution steps found - playbook may not have started or is stuck at initialization"
                            except Exception as diag_error:
                                logger.warning(f"Failed to gather diagnostic info for timed out task {task.id}: {diag_error}")
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
                                completed_at=datetime.utcnow()
                            )

                            # Update execution_context
                            self.tasks_store.update_task(task.id, execution_context=execution_context)

                            # Create error TimelineItem for timed out task
                            error_timeline_item = TimelineItem(
                                id=str(uuid.uuid4()),
                                workspace_id=task.workspace_id,
                                message_id=task.message_id,
                                task_id=task.id,
                                type=TimelineItemType.ERROR,
                                title=self.i18n.t(
                                    "conversation_orchestrator",
                                    "timeline.task_timeout_title",
                                    default="Task Timed Out"
                                ),
                                summary=self.i18n.t(
                                    "conversation_orchestrator",
                                    "timeline.task_timeout_summary",
                                    timeout_minutes=timeout_minutes,
                                    default=f"Task timed out after {timeout_minutes} minutes"
                                ),
                                data={
                                    "error": timeout_error,
                                    "task_id": task.id,
                                    "pack_id": task.pack_id,
                                    "timeout_minutes": timeout_minutes
                                },
                                cta=None,
                                created_at=datetime.utcnow()
                            )
                            self.timeline_items_store.create_timeline_item(error_timeline_item)

                            timed_out_task_ids.append(task.id)
                            logger.info(f"Task {task.id} marked as timed out and failed")

                        except Exception as e:
                            logger.error(f"Failed to mark task {task.id} as timed out: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to check for timed out tasks: {e}", exc_info=True)

        return timed_out_task_ids
        try:
            # Get all RUNNING tasks
            running_tasks = self.tasks_store.list_tasks_by_workspace(
                workspace_id=None,  # Get all workspaces
                status=TaskStatus.RUNNING,
                limit=1000  # Large limit to check all running tasks
            )

            if not running_tasks:
                return timed_out_task_ids

            timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)

            for task in running_tasks:
                # Check if task has been running too long
                # Use started_at if available, otherwise use created_at
                start_time = task.started_at or task.created_at
                if start_time:
                    # Ensure both times are timezone-naive for comparison
                    # start_time from database is already timezone-naive (UTC)
                    # timeout_threshold is also timezone-naive (UTC from datetime.utcnow())
                    if start_time < timeout_threshold:
                        # Task has timed out
                        try:
                            timeout_error = f"Task timed out after {timeout_minutes} minutes. Started at {start_time.isoformat()}"
                            logger.warning(f"Task {task.id} timed out, marking as failed: {timeout_error}")

                            # Update task status to FAILED
                            self.tasks_store.update_task_status(
                                task_id=task.id,
                                status=TaskStatus.FAILED,
                                error=timeout_error,
                                completed_at=datetime.utcnow()
                            )

                            # Create error TimelineItem for timed out task
                            error_timeline_item = TimelineItem(
                                id=str(uuid.uuid4()),
                                workspace_id=task.workspace_id,
                                message_id=task.message_id,
                                task_id=task.id,
                                type=TimelineItemType.ERROR,
                                title=self.i18n.t(
                                    "conversation_orchestrator",
                                    "timeline.task_timeout_title",
                                    default="Task Timed Out"
                                ),
                                summary=self.i18n.t(
                                    "conversation_orchestrator",
                                    "timeline.task_timeout_summary",
                                    timeout_minutes=timeout_minutes,
                                    default=f"Task timed out after {timeout_minutes} minutes"
                                ),
                                data={
                                    "error": timeout_error,
                                    "task_id": task.id,
                                    "pack_id": task.pack_id,
                                    "timeout_minutes": timeout_minutes
                                },
                                cta=None,
                                created_at=datetime.utcnow()
                            )
                            self.timeline_items_store.create_timeline_item(error_timeline_item)

                            timed_out_task_ids.append(task.id)
                            logger.info(f"Task {task.id} marked as timed out and failed")

                        except Exception as e:
                            logger.error(f"Failed to mark task {task.id} as timed out: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Failed to check for timed out tasks: {e}", exc_info=True)

        return timed_out_task_ids
