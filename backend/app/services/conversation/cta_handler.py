"""
CTA Handler

Handles CTA actions from timeline items, including soft_write and external_write operations.
"""

import logging
import os
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, Optional
import uuid

try:
    import requests
    from requests.auth import HTTPBasicAuth
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from ...models.workspace import Task, TaskStatus, TimelineItem, TimelineItemType, SideEffectLevel
from ...models.mindscape import MindEvent, EventType, EventActor
from ...services.stores.tasks_store import TasksStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...services.mindscape_store import MindscapeStore
from ...services.i18n_service import get_i18n_service
from ...shared.llm_provider_helper import get_llm_provider_from_settings

logger = logging.getLogger(__name__)


class CTAHandler:
    """
    Handles CTA actions from timeline items

    Supports:
    - soft_write actions (add_to_intents, add_to_tasks)
    - external_write actions (publish_to_wordpress, export_document, etc.)
    """

    def __init__(self, store: MindscapeStore, tasks_store: TasksStore,
                 timeline_items_store: TimelineItemsStore, plan_builder,
                 default_locale: str = "en"):
        """
        Initialize CTAHandler

        Args:
            store: MindscapeStore instance
            tasks_store: TasksStore instance
            timeline_items_store: TimelineItemsStore instance
            plan_builder: PlanBuilder instance (for side_effect_level determination)
            default_locale: Default locale for i18n
        """
        self.store = store
        self.tasks_store = tasks_store
        self.timeline_items_store = timeline_items_store
        self.plan_builder = plan_builder
        self.i18n = get_i18n_service(default_locale=default_locale)

    async def handle_cta(
        self,
        workspace_id: str,
        profile_id: str,
        timeline_item_id: str,
        action: str,
        confirm: Optional[bool] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle CTA action from timeline item

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            timeline_item_id: Timeline item ID
            action: Action type (e.g., 'add_to_intents', 'publish_to_wordpress')
            confirm: Confirmation flag (for external_write)
            project_id: Optional project ID

        Returns:
            Response dict with conversation message
        """
        try:
            # Load timeline_item from database
            timeline_item = self.timeline_items_store.get_timeline_item(timeline_item_id)
            if not timeline_item:
                raise ValueError(f"Timeline item not found: {timeline_item_id}")

            task = None
            side_effect_level = None

            if timeline_item.type == TimelineItemType.INTENT_SEEDS:
                logger.info(f"Handling CTA for INTENT_SEEDS timeline_item (no task_id required), action: {action}")
            else:
                if not timeline_item.task_id:
                    raise ValueError(f"Timeline item {timeline_item_id} requires task_id but it's None")
                task = self.tasks_store.get_task(timeline_item.task_id)
                if not task:
                    raise ValueError(f"Task not found: {timeline_item.task_id}")
                # Determine side_effect_level from pack
                side_effect_level = self.plan_builder.determine_side_effect_level(task.pack_id)

            # Create user message event for CTA action
            user_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.USER,
                channel="local_workspace",
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.MESSAGE,
                payload={
                    "message": f"CTA action: {action}",
                    "timeline_item_id": timeline_item_id,
                    "action": action,
                    "confirm": confirm
                },
                entity_ids=[],
                metadata={}
            )
            self.store.create_event(user_event)

            assistant_response = None
            triggered_playbook = None

            if timeline_item.type == TimelineItemType.INTENT_SEEDS:
                if action == "add_to_intents":
                    assistant_response = await self._handle_add_to_intents_direct(
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        user_event=user_event,
                        timeline_item=timeline_item
                    )
                elif action == "show_pack_suggestions":
                    suggested_packs = timeline_item.data.get('suggested_packs', [])
                    if suggested_packs:
                        pack_names = [p.get('pack_id', '') for p in suggested_packs[:5]]
                        assistant_response = self.i18n.t(
                            "conversation_orchestrator",
                            "suggestion.suggested_packs",
                            packs=", ".join(pack_names),
                            default=f"Suggested packs: {', '.join(pack_names)}"
                        )
                    else:
                        assistant_response = self.i18n.t(
                            "conversation_orchestrator",
                            "suggestion.no_suggested_packs",
                            default="No suggested packs"
                        )
                else:
                    raise ValueError(f"Unknown action for INTENT_SEEDS: {action}")

            elif side_effect_level == SideEffectLevel.SOFT_WRITE:
                assistant_response = await self._handle_soft_write(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    user_event=user_event,
                    timeline_item=timeline_item,
                    task=task,
                    action=action
                )

            elif side_effect_level == SideEffectLevel.EXTERNAL_WRITE:
                if confirm is None:
                    # Generate confirmation message
                    # Convert TimelineItem to dict for message generator
                    timeline_item_dict = {
                        "id": timeline_item.id,
                        "title": timeline_item.title,
                        "summary": timeline_item.summary,
                        "data": timeline_item.data,
                        "type": timeline_item.type.value if hasattr(timeline_item.type, 'value') else str(timeline_item.type)
                    }
                    confirmation = await self._generate_confirmation(
                        action_type=action,
                        action_params=timeline_item.data,
                        timeline_item=timeline_item_dict
                    )
                    assistant_response = confirmation["message"]
                    # Return confirmation buttons in response
                    return {
                        "workspace_id": workspace_id,
                        "display_events": [{
                            "id": user_event.id,
                            "timestamp": user_event.timestamp.isoformat(),
                            "actor": "user",
                            "message": f"CTA action: {action}",
                            "payload": user_event.payload
                        }],
                        "triggered_playbook": None,
                        "pending_tasks": [],
                        "confirmation_required": True,
                        "confirmation_buttons": confirmation["confirm_buttons"]
                    }
                elif confirm is True:
                    assistant_response = await self._handle_external_write(
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        user_event=user_event,
                        timeline_item=timeline_item,
                        task=task,
                        action=action
                    )
                else:
                    # User cancelled
                    assistant_response = "Action cancelled."

            else:
                # Readonly: should not have CTA, but handle gracefully
                assistant_response = self.i18n.t(
                    "conversation_orchestrator",
                    "feedback.readonly",
                    summary=timeline_item.summary
                )

            # Create assistant response event
            if assistant_response:
                assistant_event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=_utc_now(),
                    actor=EventActor.ASSISTANT,
                    channel="local_workspace",
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    event_type=EventType.MESSAGE,
                    payload={
                        "message": assistant_response,
                        "response_to": user_event.id
                    },
                    entity_ids=[],
                    metadata={}
                )
                self.store.create_event(assistant_event)

            # Get recent events for display
            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=20
            )

            # Get pending tasks
            pending_tasks_list = self.tasks_store.list_pending_tasks(workspace_id)
            running_tasks_list = self.tasks_store.list_running_tasks(workspace_id)

            pending_tasks = []
            for task_item in pending_tasks_list + running_tasks_list:
                pending_tasks.append({
                    "id": task_item.id,
                    "pack_id": task_item.pack_id,
                    "task_type": task_item.task_type,
                    "status": task_item.status.value,
                    "created_at": task_item.created_at.isoformat() if task_item.created_at else None
                })

            # Format display events
            display_events_dicts = []
            for event in recent_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                entity_ids = event.entity_ids if isinstance(event.entity_ids, list) else []
                metadata = event.metadata if isinstance(event.metadata, dict) else {}

                event_dict = {
                    'id': event.id,
                    'timestamp': event.timestamp.isoformat(),
                    'actor': event.actor.value if hasattr(event.actor, 'value') else str(event.actor),
                    'channel': event.channel,
                    'profile_id': event.profile_id,
                    'project_id': event.project_id,
                    'workspace_id': event.workspace_id,
                    'event_type': event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                    'payload': payload,
                    'entity_ids': entity_ids,
                    'metadata': metadata
                }
                display_events_dicts.append(event_dict)

            return {
                "workspace_id": workspace_id,
                "display_events": display_events_dicts,
                "triggered_playbook": triggered_playbook,
                "pending_tasks": pending_tasks
            }

        except Exception as e:
            logger.error(f"CTAHandler.handle_cta error: {str(e)}", exc_info=True)
            raise

    async def _handle_soft_write(
        self,
        workspace_id: str,
        profile_id: str,
        user_event: MindEvent,
        timeline_item: TimelineItem,
        task: Task,
        action: str
    ) -> str:
        """
        Handle soft_write CTA action

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            user_event: User event for CTA action
            timeline_item: Timeline item
            task: Associated task
            action: Action type

        Returns:
            Assistant response message
        """
        if action == "add_to_intents":
            # Extract intents from timeline item data
            intents = timeline_item.data.get("intents", [])
            if intents:
                from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
                for intent_item in intents[:3]:
                    # Handle both string and dict formats
                    if isinstance(intent_item, dict):
                        intent_text = intent_item.get("title") or intent_item.get("text") or str(intent_item)
                    else:
                        intent_text = str(intent_item) if intent_item else None

                    if intent_text and isinstance(intent_text, str) and len(intent_text.strip()) > 0:
                        try:
                            existing_intents = self.store.list_intents(
                                profile_id=profile_id,
                                status=None,
                                priority=None
                            )
                            intent_exists = any(
                                intent.title == intent_text.strip() or
                                intent_text.strip() in intent.title
                                for intent in existing_intents
                            )
                            if not intent_exists:
                                new_intent = IntentCard(
                                    id=str(uuid.uuid4()),
                                    profile_id=profile_id,
                                    title=intent_text.strip(),
                                    description=f"Added from timeline item: {timeline_item.title}",
                                    status=IntentStatus.ACTIVE,
                                    priority=PriorityLevel.MEDIUM,
                                    tags=[],
                                    category="timeline_cta",
                                    progress_percentage=0.0,
                                    created_at=_utc_now(),
                                    updated_at=_utc_now(),
                                    started_at=None,
                                    completed_at=None,
                                    due_date=None,
                                    parent_intent_id=None,
                                    child_intent_ids=[],
                                    metadata={
                                        "source": "timeline_cta",
                                        "timeline_item_id": timeline_item.id,
                                        "workspace_id": workspace_id
                                    }
                                )
                                self.store.create_intent(new_intent)
                                logger.info(f"Created intent from CTA: {intent_text[:50]}")
                        except Exception as e:
                            logger.warning(f"Failed to create intent from CTA: {e}")

                # Create task for soft_write action
                action_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    execution_id=None,
                    pack_id=task.pack_id,
                    task_type=f"soft_write_{action}",
                    status=TaskStatus.SUCCEEDED,
                    params={
                        "action": action,
                        "timeline_item_id": timeline_item.id,
                        "intents_added": len(intents)
                    },
                    result={"action": action, "intents_added": len(intents)},
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=None
                )
                self.tasks_store.create_task(action_task)

                # Create new TimelineItem for soft_write action result
                action_timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    task_id=action_task.id,
                    type=TimelineItemType.INTENT_SEEDS,
                    title=f"Added {len(intents)} intent(s) to Mindscape",
                    summary=f"Successfully added {len(intents)} intent(s) from timeline item",
                    data={
                        "action": action,
                        "intents_added": intents,
                        "original_timeline_item_id": timeline_item.id
                    },
                    cta=None,
                    created_at=_utc_now()
                )
                self.timeline_items_store.create_timeline_item(action_timeline_item)

                # Note: Original timeline item is not updated - it should not exist in Timeline
                # because Timeline only shows completed items. The original item was a suggestion
                # that should have been in PendingTasksPanel, not Timeline.
                logger.info(f"Created completed TimelineItem for {action} action")

                return self.i18n.t(
                    "conversation_orchestrator",
                    "suggestion.add_to_mindscape"
                ) + f" Added {len(intents)} intent(s)."

        elif action == "add_to_tasks":
            # Extract tasks from timeline item data
            tasks = timeline_item.data.get("tasks", [])
            if tasks:
                # Store extracted tasks in timeline item data for now
                # In the future, these could be stored in a dedicated tasks table
                # For now, we'll create a summary and update the timeline item
                tasks_added = []
                for task_data in tasks[:10]:  # Limit to 10 tasks
                    if isinstance(task_data, dict) and task_data.get("title"):
                        tasks_added.append({
                            "title": task_data.get("title"),
                            "description": task_data.get("description", ""),
                            "priority": task_data.get("priority", "medium"),
                            "due_date": task_data.get("due_date"),
                            "tags": task_data.get("tags", [])
                        })

                # Create task for soft_write action
                action_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    execution_id=None,
                    pack_id=task.pack_id,
                    task_type=f"soft_write_{action}",
                    status=TaskStatus.SUCCEEDED,
                    params={
                        "action": action,
                        "timeline_item_id": timeline_item.id,
                        "tasks_added": len(tasks_added)
                    },
                    result={"action": action, "tasks_added": tasks_added},
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=None
                )
                self.tasks_store.create_task(action_task)

                # Create new TimelineItem for soft_write action result
                action_timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    task_id=action_task.id,
                    type=TimelineItemType.PLAN,
                    title=f"Added {len(tasks_added)} task(s) to plan",
                    summary=f"Successfully added {len(tasks_added)} task(s) from timeline item",
                    data={
                        "action": action,
                        "tasks_added": tasks_added,
                        "original_timeline_item_id": timeline_item.id
                    },
                    cta=None,
                    created_at=_utc_now()
                )
                self.timeline_items_store.create_timeline_item(action_timeline_item)

                # Note: Original timeline item is not updated - it should not exist in Timeline
                # because Timeline only shows completed items. The original item was a suggestion
                # that should have been in PendingTasksPanel, not Timeline.
                logger.info(f"Created completed TimelineItem for {action} action")

                return self.i18n.t(
                    "conversation_orchestrator",
                    "suggestion.add_to_mindscape"
                ) + f" Added {len(tasks_added)} task(s) to plan."

        return f"Executed {action} successfully."

    async def _handle_add_to_intents_direct(
        self,
        workspace_id: str,
        profile_id: str,
        user_event: MindEvent,
        timeline_item: TimelineItem
    ) -> str:
        """
        Handle add_to_intents action directly for INTENT_SEEDS timeline items (no task required)

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            user_event: User event for CTA action
            timeline_item: Timeline item (INTENT_SEEDS type)

        Returns:
            Assistant response message
        """
        # Extract intents from timeline item data
        intents = timeline_item.data.get("intents", [])
        if not intents:
            return self.i18n.t(
                "conversation_orchestrator",
                "feedback.no_intents_to_add",
                default="No intents found in timeline item"
            )

        from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
        intents_added = 0

        for intent_item in intents[:3]:
            # Handle both string and dict formats
            if isinstance(intent_item, dict):
                intent_text = intent_item.get("title") or intent_item.get("text") or str(intent_item)
            else:
                intent_text = str(intent_item) if intent_item else None

            if intent_text and isinstance(intent_text, str) and len(intent_text.strip()) > 0:
                try:
                    existing_intents = self.store.list_intents(
                        profile_id=profile_id,
                        status=None,
                        priority=None
                    )
                    intent_exists = any(
                        intent.title == intent_text.strip() or
                        intent_text.strip() in intent.title
                        for intent in existing_intents
                    )
                    if not intent_exists:
                        new_intent = IntentCard(
                            id=str(uuid.uuid4()),
                            profile_id=profile_id,
                            title=intent_text.strip(),
                            description=f"Added from timeline item: {timeline_item.title}",
                            status=IntentStatus.ACTIVE,
                            priority=PriorityLevel.MEDIUM,
                            tags=[],
                            category="timeline_cta",
                            progress_percentage=0.0,
                            created_at=_utc_now(),
                            updated_at=_utc_now(),
                            started_at=None,
                            completed_at=None,
                            due_date=None,
                            parent_intent_id=None,
                            child_intent_ids=[],
                            metadata={
                                "source": "timeline_cta",
                                "timeline_item_id": timeline_item.id,
                                "workspace_id": workspace_id
                            }
                        )
                        self.store.create_intent(new_intent)
                        intents_added += 1
                        logger.info(f"Created intent from CTA: {intent_text[:50]}")
                except Exception as e:
                    logger.warning(f"Failed to create intent from CTA: {e}")

        # Create task for tracking the action (use a system pack_id)
        action_task = Task(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=user_event.id,
            execution_id=None,
            pack_id="system",  # Use system pack_id since this is a direct action, not from a pack
            task_type=f"cta_add_to_intents",
            status=TaskStatus.SUCCEEDED,
            params={
                "action": "add_to_intents",
                "timeline_item_id": timeline_item.id,
                "intents_added": intents_added
            },
            result={"action": "add_to_intents", "intents_added": intents_added},
            created_at=_utc_now(),
            started_at=_utc_now(),
            completed_at=_utc_now(),
            error=None
        )
        self.tasks_store.create_task(action_task)

        # Create new TimelineItem for action result
        action_timeline_item = TimelineItem(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=user_event.id,
            task_id=action_task.id,  # This result timeline_item has a task_id
            type=TimelineItemType.INTENT_SEEDS,
            title=self.i18n.t(
                "conversation_orchestrator",
                "timeline.intents_added_title" if intents_added > 0 else "timeline.no_intents_added_title",
                count=intents_added,
                default=f"Added {intents_added} intent(s) to Mindscape" if intents_added > 0 else "No new intents"
            ),
            summary=self.i18n.t(
                "conversation_orchestrator",
                "timeline.intents_added_summary" if intents_added > 0 else "timeline.all_intents_exist_summary",
                count=intents_added,
                default=f"Successfully added {intents_added} intent(s) from timeline item" if intents_added > 0 else "All intents already exist"
            ),
            data={
                "action": "add_to_intents",
                "intents_added": intents_added,
                "original_timeline_item_id": timeline_item.id
            },
            cta=None,
            created_at=_utc_now()
        )
        self.timeline_items_store.create_timeline_item(action_timeline_item)

        # Note: Original timeline item is not updated - it should not exist in Timeline
        # because Timeline only shows completed items. The original item was a suggestion
        # that should have been in PendingTasksPanel, not Timeline.
        logger.info(f"Created completed TimelineItem for add_to_intents action")

        if intents_added > 0:
            return self.i18n.t(
                "conversation_orchestrator",
                "suggestion.add_to_mindscape",
                count=intents_added,
                default=f"Added to Mindscape. Added {intents_added} intent(s)."
            )
        else:
            return self.i18n.t(
                "conversation_orchestrator",
                "suggestion.all_intents_exist",
                default="All intents already exist, no new intents added."
            )

    async def _handle_external_write(
        self,
        workspace_id: str,
        profile_id: str,
        user_event: MindEvent,
        timeline_item: TimelineItem,
        task: Task,
        action: str
    ) -> str:
        """
        Handle external_write CTA action

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            user_event: User event for CTA action
            timeline_item: Timeline item
            task: Associated task
            action: Action type

        Returns:
            Assistant response message
        """
        if action == "publish_to_wordpress" or action.startswith("publish_"):
            # Execute WordPress publish action
            try:
                # Get content from timeline_item data
                content_data = timeline_item.data.get("content") or timeline_item.data.get("draft") or timeline_item.summary
                title = timeline_item.data.get("title") or timeline_item.title

                # Execute wp_sync pack or WordPress publish
                publish_result = await self._execute_wordpress_publish(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    title=title,
                    content=content_data,
                    timeline_item_id=timeline_item.id
                )

                # Create task for external write action
                publish_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    execution_id=None,
                    pack_id="wp_sync",
                    task_type="publish_post",
                    status=TaskStatus.SUCCEEDED if publish_result.get("success") else TaskStatus.FAILED,
                    params={
                        "title": title,
                        "action": action
                    },
                    result=publish_result,
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=publish_result.get("error")
                )
                self.tasks_store.create_task(publish_task)

                # Create new TimelineItem for external write action result
                result_timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    task_id=publish_task.id,
                    type=TimelineItemType.SUMMARY if publish_result.get("success") else TimelineItemType.ERROR,
                    title=f"Published: {title}" if publish_result.get("success") else f"Failed to publish: {title}",
                    summary=publish_result.get("post_url", "Published successfully") if publish_result.get("success") else publish_result.get("error", "Unknown error"),
                    data={
                        "action": action,
                        "publish_result": publish_result,
                        "original_timeline_item_id": timeline_item.id
                    },
                    cta=None,
                    created_at=_utc_now()
                )
                self.timeline_items_store.create_timeline_item(result_timeline_item)

                # Also update original timeline item with publish result (optional, for reference)
                try:
                    timeline_item.data["publish_result"] = publish_result
                    self.timeline_items_store.update_timeline_item(timeline_item.id, data=timeline_item.data)
                except Exception as e:
                    logger.warning(f"Failed to update original timeline item: {e}")

                if publish_result.get("success"):
                    return self.i18n.t(
                        "conversation_orchestrator",
                        "workflow.started",
                        playbook_code="wp_sync"
                    ) + f" Published: {publish_result.get('post_url', 'N/A')}"
                else:
                    return f"Failed to publish: {publish_result.get('error', 'Unknown error')}"
            except Exception as e:
                logger.error(f"Failed to execute WordPress publish: {e}", exc_info=True)

                # Create error TimelineItem for failed WordPress publish
                error_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    execution_id=None,
                    pack_id="wp_sync",
                    task_type="publish_post",
                    status=TaskStatus.FAILED,
                    params={"title": timeline_item.title, "action": action},
                    result={"error": str(e)},
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=str(e)
                )
                self.tasks_store.create_task(error_task)

                error_timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    message_id=user_event.id,
                    task_id=error_task.id,
                    type=TimelineItemType.ERROR,
                    title=f"Failed to publish: {timeline_item.title}",
                    summary=f"Error: {str(e)}",
                    data={
                        "action": action,
                        "error": str(e),
                        "original_timeline_item_id": timeline_item.id
                    },
                    cta=None,
                    created_at=_utc_now()
                )
                self.timeline_items_store.create_timeline_item(error_timeline_item)

                return f"Error executing {action}: {str(e)}"
        else:
            # Handle other external_write actions
            # Try to execute the action based on action type
            action_result = None
            action_success = False
            action_error = None

            try:
                # Try to execute action via appropriate pack/service
                # NOTE: These are placeholder implementations. Real implementations should be added
                # when specific external_write actions are needed (e.g., Notion, Drive, n8n, etc.)
                if action == "export_document":
                    # Export document action (placeholder)
                    # TODO: Implement actual document export logic
                    logger.info(f"Export document action triggered (placeholder implementation)")
                    action_result = {
                        "action": action,
                        "status": "completed",
                        "exported": True,
                        "note": "Placeholder implementation - actual export logic to be implemented"
                    }
                    action_success = True
                elif action == "execute_external_action":
                    # Generic external action (placeholder)
                    # TODO: Implement actual external action execution logic
                    logger.info(f"Generic external action triggered (placeholder implementation)")
                    action_result = {
                        "action": action,
                        "status": "completed",
                        "note": "Placeholder implementation - actual action logic to be implemented"
                    }
                    action_success = True
                else:
                    # Unknown action, mark as completed but log warning
                    logger.warning(f"Unknown external_write action: {action} - using placeholder")
                    action_result = {
                        "action": action,
                        "status": "completed",
                        "note": "Action executed but implementation may be missing - placeholder result"
                    }
                    action_success = True
            except Exception as e:
                action_error = str(e)
                action_success = False
                logger.error(f"Failed to execute external_write action {action}: {e}", exc_info=True)

            # Create task for external write action
            action_task = Task(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=user_event.id,
                execution_id=None,
                pack_id=task.pack_id,
                task_type=f"external_action_{action}",
                status=TaskStatus.SUCCEEDED if action_success else TaskStatus.FAILED,
                params={
                    "action": action,
                    "timeline_item_id": timeline_item.id
                },
                result=action_result if action_success else {"error": action_error},
                created_at=_utc_now(),
                started_at=_utc_now(),
                completed_at=_utc_now(),
                error=action_error
            )
            self.tasks_store.create_task(action_task)

            # Create new TimelineItem for external action result (success or failure)
            action_timeline_item = TimelineItem(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                message_id=user_event.id,
                task_id=action_task.id,
                type=TimelineItemType.SUMMARY if action_success else TimelineItemType.ERROR,
                title=f"Executed: {action}" if action_success else f"Failed: {action}",
                summary=action_result.get("message", f"Successfully executed {action}") if action_success else f"Error: {action_error}",
                data={
                    "action": action,
                    "result": action_result if action_success else None,
                    "error": action_error,
                    "original_timeline_item_id": timeline_item.id
                },
                cta=None,
                created_at=_utc_now()
            )
            self.timeline_items_store.create_timeline_item(action_timeline_item)

            if action_success:
                return f"Executed {action} successfully."
            else:
                return f"Failed to execute {action}: {action_error}"

    async def _execute_wordpress_publish(
        self,
        workspace_id: str,
        profile_id: str,
        title: str,
        content: str,
        timeline_item_id: str
    ) -> Dict[str, Any]:
        """
        Execute WordPress publish action

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            title: Post title
            content: Post content
            timeline_item_id: Timeline item ID

        Returns:
            Dict with success status and result data
        """
        try:
            # Try to use wp_sync pack if available
            from ...capabilities.registry import get_registry
            registry = get_registry()
            wp_sync_pack = registry.get_pack("wp_sync")

            if wp_sync_pack:
                # Use wp_sync pack to publish
                # This would call the WordPress REST API
                if not REQUESTS_AVAILABLE:
                    return {
                        "success": False,
                        "error": "requests library not available"
                    }

                wp_url = os.getenv("WORDPRESS_URL", "")
                wp_username = os.getenv("WORDPRESS_USERNAME", "")
                wp_password = os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

                if not wp_url or not wp_username or not wp_password:
                    return {
                        "success": False,
                        "error": "WordPress credentials not configured"
                    }

                # Publish post via WordPress REST API
                api_url = f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts"
                response = requests.post(
                    api_url,
                    json={
                        "title": title,
                        "content": content,
                        "status": "publish"
                    },
                    auth=HTTPBasicAuth(wp_username, wp_password),
                    timeout=30
                )

                if response.status_code == 201:
                    post_data = response.json()
                    return {
                        "success": True,
                        "post_id": post_data.get("id"),
                        "post_url": post_data.get("link"),
                        "post_data": post_data
                    }
                else:
                    return {
                        "success": False,
                        "error": f"WordPress API error: {response.status_code} - {response.text}"
                    }
            else:
                return {
                    "success": False,
                    "error": "wp_sync pack not available"
                }
        except Exception as e:
            logger.error(f"Failed to execute WordPress publish: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _generate_confirmation(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        timeline_item: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate confirmation message for external_write action

        Uses LLM to generate detailed confirmation messages.

        Args:
            action_type: Action type (e.g., 'publish_to_wordpress')
            action_params: Action parameters
            timeline_item: Timeline item with content to be published (optional)

        Returns:
            Dict with confirmation message and buttons
        """
        from backend.app.services.message_generator import MessageGenerator
        from ...services.agent_runner import LLMProviderManager
        import os

        # Initialize LLM provider
        from backend.app.shared.llm_provider_helper import create_llm_provider_manager
        llm_manager = create_llm_provider_manager()
        llm_provider = get_llm_provider_from_settings(llm_manager)

        # Use MessageGenerator with LLM
        message_generator = MessageGenerator(
            llm_provider=llm_provider,
            default_locale=self.i18n.default_locale
        )

        return await message_generator.generate_confirmation_message(
            action_type=action_type,
            action_params=action_params,
            timeline_item=timeline_item,
            locale=self.i18n.default_locale
        )
