"""Top-level CTA dispatch flow."""

import logging
import uuid
from typing import Any, Dict, Optional

from ....models.mindscape import EventActor, EventType, MindEvent
from ....models.workspace import SideEffectLevel, TimelineItemType
from .base import _utc_now

logger = logging.getLogger(__name__)


class CTAOrchestratorMixin:
    """Dispatch CTA actions from timeline items."""

    async def handle_cta(
        self,
        workspace_id: str,
        profile_id: str,
        timeline_item_id: str,
        action: str,
        confirm: Optional[bool] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle CTA action from timeline item.

        Args:
            workspace_id: Workspace ID.
            profile_id: User profile ID.
            timeline_item_id: Timeline item ID.
            action: Action type.
            confirm: Confirmation flag.
            project_id: Optional project ID.

        Returns:
            Response dict with conversation message.
        """
        try:
            timeline_item = self.timeline_items_store.get_timeline_item(
                timeline_item_id
            )
            if not timeline_item:
                raise ValueError(f"Timeline item not found: {timeline_item_id}")

            task = None
            side_effect_level = None

            if timeline_item.type == TimelineItemType.INTENT_SEEDS:
                logger.info(
                    f"Handling CTA for INTENT_SEEDS timeline_item (no task_id required), action: {action}"
                )
            else:
                if not timeline_item.task_id:
                    raise ValueError(
                        f"Timeline item {timeline_item_id} requires task_id but it's None"
                    )
                task = self.tasks_store.get_task(timeline_item.task_id)
                if not task:
                    raise ValueError(f"Task not found: {timeline_item.task_id}")
                side_effect_level = self.plan_builder.determine_side_effect_level(
                    task.pack_id
                )

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
                    "confirm": confirm,
                },
                entity_ids=[],
                metadata={},
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
                        timeline_item=timeline_item,
                    )
                elif action == "show_pack_suggestions":
                    suggested_packs = timeline_item.data.get("suggested_packs", [])
                    if suggested_packs:
                        pack_names = [p.get("pack_id", "") for p in suggested_packs[:5]]
                        assistant_response = self.i18n.t(
                            "conversation_orchestrator",
                            "suggestion.suggested_packs",
                            packs=", ".join(pack_names),
                            default=f"Suggested packs: {', '.join(pack_names)}",
                        )
                    else:
                        assistant_response = self.i18n.t(
                            "conversation_orchestrator",
                            "suggestion.no_suggested_packs",
                            default="No suggested packs",
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
                    action=action,
                )

            elif side_effect_level == SideEffectLevel.EXTERNAL_WRITE:
                if confirm is None:
                    timeline_item_dict = {
                        "id": timeline_item.id,
                        "title": timeline_item.title,
                        "summary": timeline_item.summary,
                        "data": timeline_item.data,
                        "type": timeline_item.type.value
                        if hasattr(timeline_item.type, "value")
                        else str(timeline_item.type),
                    }
                    confirmation = await self._generate_confirmation(
                        action_type=action,
                        action_params=timeline_item.data,
                        timeline_item=timeline_item_dict,
                    )
                    assistant_response = confirmation["message"]
                    return {
                        "workspace_id": workspace_id,
                        "display_events": [
                            {
                                "id": user_event.id,
                                "timestamp": user_event.timestamp.isoformat(),
                                "actor": "user",
                                "message": f"CTA action: {action}",
                                "payload": user_event.payload,
                            }
                        ],
                        "triggered_playbook": None,
                        "pending_tasks": [],
                        "confirmation_required": True,
                        "confirmation_buttons": confirmation["confirm_buttons"],
                    }
                elif confirm is True:
                    assistant_response = await self._handle_external_write(
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        user_event=user_event,
                        timeline_item=timeline_item,
                        task=task,
                        action=action,
                    )
                else:
                    assistant_response = "Action cancelled."

            else:
                assistant_response = self.i18n.t(
                    "conversation_orchestrator",
                    "feedback.readonly",
                    summary=timeline_item.summary,
                )

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
                        "response_to": user_event.id,
                    },
                    entity_ids=[],
                    metadata={},
                )
                self.store.create_event(assistant_event)

            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=20,
            )

            pending_tasks_list = self.tasks_store.list_pending_tasks(workspace_id)
            running_tasks_list = self.tasks_store.list_running_tasks(workspace_id)

            pending_tasks = []
            for task_item in pending_tasks_list + running_tasks_list:
                pending_tasks.append(
                    {
                        "id": task_item.id,
                        "pack_id": task_item.pack_id,
                        "task_type": task_item.task_type,
                        "status": task_item.status.value,
                        "created_at": task_item.created_at.isoformat()
                        if task_item.created_at
                        else None,
                    }
                )

            display_events_dicts = []
            for event in recent_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                entity_ids = (
                    event.entity_ids if isinstance(event.entity_ids, list) else []
                )
                metadata = event.metadata if isinstance(event.metadata, dict) else {}

                event_dict = {
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat(),
                    "actor": event.actor.value
                    if hasattr(event.actor, "value")
                    else str(event.actor),
                    "channel": event.channel,
                    "profile_id": event.profile_id,
                    "project_id": event.project_id,
                    "workspace_id": event.workspace_id,
                    "event_type": event.event_type.value
                    if hasattr(event.event_type, "value")
                    else str(event.event_type),
                    "payload": payload,
                    "entity_ids": entity_ids,
                    "metadata": metadata,
                }
                display_events_dicts.append(event_dict)

            return {
                "workspace_id": workspace_id,
                "display_events": display_events_dicts,
                "triggered_playbook": triggered_playbook,
                "pending_tasks": pending_tasks,
            }

        except Exception as e:
            logger.error(f"CTAHandler.handle_cta error: {str(e)}", exc_info=True)
            raise
