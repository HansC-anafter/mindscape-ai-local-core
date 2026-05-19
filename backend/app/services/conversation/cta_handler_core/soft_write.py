"""Soft-write CTA action handlers."""

import logging
import uuid

from ....models.mindscape import MindEvent
from ....models.workspace import Task, TaskStatus, TimelineItem, TimelineItemType
from .base import _utc_now

logger = logging.getLogger(__name__)


class CTASoftWriteMixin:
    """Handle local soft-write CTA actions."""

    async def _handle_soft_write(
        self,
        workspace_id: str,
        profile_id: str,
        user_event: MindEvent,
        timeline_item: TimelineItem,
        task: Task,
        action: str,
    ) -> str:
        """
        Handle soft_write CTA action.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            user_event: User event for CTA action.
            timeline_item: Timeline item.
            task: Associated task.
            action: Action type.

        Returns:
            Assistant response message.
        """
        if action == "add_to_intents":
            intents = timeline_item.data.get("intents", [])
            if intents:
                from ....models.mindscape import IntentCard, IntentStatus, PriorityLevel

                for intent_item in intents[:3]:
                    if isinstance(intent_item, dict):
                        intent_text = (
                            intent_item.get("title")
                            or intent_item.get("text")
                            or str(intent_item)
                        )
                    else:
                        intent_text = str(intent_item) if intent_item else None

                    if (
                        intent_text
                        and isinstance(intent_text, str)
                        and len(intent_text.strip()) > 0
                    ):
                        try:
                            existing_intents = self.store.list_intents(
                                profile_id=profile_id,
                                status=None,
                                priority=None,
                            )
                            intent_exists = any(
                                intent.title == intent_text.strip()
                                or intent_text.strip() in intent.title
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
                                        "workspace_id": workspace_id,
                                    },
                                )
                                self.store.create_intent(new_intent)
                                logger.info(
                                    f"Created intent from CTA: {intent_text[:50]}"
                                )
                        except Exception as e:
                            logger.warning(f"Failed to create intent from CTA: {e}")

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
                        "intents_added": len(intents),
                    },
                    result={"action": action, "intents_added": len(intents)},
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=None,
                )
                self.tasks_store.create_task(action_task)

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
                        "original_timeline_item_id": timeline_item.id,
                    },
                    cta=None,
                    created_at=_utc_now(),
                )
                self.timeline_items_store.create_timeline_item(action_timeline_item)

                logger.info(f"Created completed TimelineItem for {action} action")

                return (
                    self.i18n.t(
                        "conversation_orchestrator",
                        "suggestion.add_to_mindscape",
                    )
                    + f" Added {len(intents)} intent(s)."
                )

        elif action == "add_to_tasks":
            tasks = timeline_item.data.get("tasks", [])
            if tasks:
                tasks_added = []
                for task_data in tasks[:10]:
                    if isinstance(task_data, dict) and task_data.get("title"):
                        tasks_added.append(
                            {
                                "title": task_data.get("title"),
                                "description": task_data.get("description", ""),
                                "priority": task_data.get("priority", "medium"),
                                "due_date": task_data.get("due_date"),
                                "tags": task_data.get("tags", []),
                            }
                        )

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
                        "tasks_added": len(tasks_added),
                    },
                    result={"action": action, "tasks_added": tasks_added},
                    created_at=_utc_now(),
                    started_at=_utc_now(),
                    completed_at=_utc_now(),
                    error=None,
                )
                self.tasks_store.create_task(action_task)

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
                        "original_timeline_item_id": timeline_item.id,
                    },
                    cta=None,
                    created_at=_utc_now(),
                )
                self.timeline_items_store.create_timeline_item(action_timeline_item)

                logger.info(f"Created completed TimelineItem for {action} action")

                return (
                    self.i18n.t(
                        "conversation_orchestrator",
                        "suggestion.add_to_mindscape",
                    )
                    + f" Added {len(tasks_added)} task(s) to plan."
                )

        return f"Executed {action} successfully."

    async def _handle_add_to_intents_direct(
        self,
        workspace_id: str,
        profile_id: str,
        user_event: MindEvent,
        timeline_item: TimelineItem,
    ) -> str:
        """
        Handle add_to_intents action directly for INTENT_SEEDS timeline items.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            user_event: User event for CTA action.
            timeline_item: INTENT_SEEDS timeline item.

        Returns:
            Assistant response message.
        """
        intents = timeline_item.data.get("intents", [])
        if not intents:
            return self.i18n.t(
                "conversation_orchestrator",
                "feedback.no_intents_to_add",
                default="No intents found in timeline item",
            )

        from ....models.mindscape import IntentCard, IntentStatus, PriorityLevel

        intents_added = 0

        for intent_item in intents[:3]:
            if isinstance(intent_item, dict):
                intent_text = (
                    intent_item.get("title")
                    or intent_item.get("text")
                    or str(intent_item)
                )
            else:
                intent_text = str(intent_item) if intent_item else None

            if (
                intent_text
                and isinstance(intent_text, str)
                and len(intent_text.strip()) > 0
            ):
                try:
                    existing_intents = self.store.list_intents(
                        profile_id=profile_id,
                        status=None,
                        priority=None,
                    )
                    intent_exists = any(
                        intent.title == intent_text.strip()
                        or intent_text.strip() in intent.title
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
                                "workspace_id": workspace_id,
                            },
                        )
                        self.store.create_intent(new_intent)
                        intents_added += 1
                        logger.info(f"Created intent from CTA: {intent_text[:50]}")
                except Exception as e:
                    logger.warning(f"Failed to create intent from CTA: {e}")

        action_task = Task(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=user_event.id,
            execution_id=None,
            pack_id="system",
            task_type="cta_add_to_intents",
            status=TaskStatus.SUCCEEDED,
            params={
                "action": "add_to_intents",
                "timeline_item_id": timeline_item.id,
                "intents_added": intents_added,
            },
            result={"action": "add_to_intents", "intents_added": intents_added},
            created_at=_utc_now(),
            started_at=_utc_now(),
            completed_at=_utc_now(),
            error=None,
        )
        self.tasks_store.create_task(action_task)

        action_timeline_item = TimelineItem(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=user_event.id,
            task_id=action_task.id,
            type=TimelineItemType.INTENT_SEEDS,
            title=self.i18n.t(
                "conversation_orchestrator",
                "timeline.intents_added_title"
                if intents_added > 0
                else "timeline.no_intents_added_title",
                count=intents_added,
                default=f"Added {intents_added} intent(s) to Mindscape"
                if intents_added > 0
                else "No new intents",
            ),
            summary=self.i18n.t(
                "conversation_orchestrator",
                "timeline.intents_added_summary"
                if intents_added > 0
                else "timeline.all_intents_exist_summary",
                count=intents_added,
                default=f"Successfully added {intents_added} intent(s) from timeline item"
                if intents_added > 0
                else "All intents already exist",
            ),
            data={
                "action": "add_to_intents",
                "intents_added": intents_added,
                "original_timeline_item_id": timeline_item.id,
            },
            cta=None,
            created_at=_utc_now(),
        )
        self.timeline_items_store.create_timeline_item(action_timeline_item)

        logger.info("Created completed TimelineItem for add_to_intents action")

        if intents_added > 0:
            return self.i18n.t(
                "conversation_orchestrator",
                "suggestion.add_to_mindscape",
                count=intents_added,
                default=f"Added to Mindscape. Added {intents_added} intent(s).",
            )
        return self.i18n.t(
            "conversation_orchestrator",
            "suggestion.all_intents_exist",
            default="All intents already exist, no new intents added.",
        )
