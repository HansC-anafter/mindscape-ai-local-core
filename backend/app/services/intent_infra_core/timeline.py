"""Timeline helpers for intent infrastructure service."""

from __future__ import annotations

import logging
import uuid
from typing import Any, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.models.workspace import TimelineItem, TimelineItemType
from backend.app.services.intent_infra_core.time import _utc_now

logger = logging.getLogger(__name__)


class TimelineCreationMixin:
    """Timeline helper methods for IntentInfraService."""

    async def _create_timeline_for_extraction(
        self,
        ctx: LocalDomainContext,
        original_message_id: str,
        task_id: str,
        intents: List[Any],
        themes: List[Any],
        intents_added: int,
    ) -> Optional[TimelineItem]:
        """
        Create TimelineItem for intent extraction activity.

        Args:
            ctx: Execution context
            original_message_id: Original message/event ID
            task_id: Task ID
            intents: List of intents
            themes: List of themes
            intents_added: Number of intents added

        Returns:
            Created TimelineItem or None
        """
        try:
            timeline_item = TimelineItem(
                id=str(uuid.uuid4()),
                workspace_id=ctx.workspace_id,
                message_id=original_message_id,
                task_id=task_id,
                type=TimelineItemType.INTENT_SEEDS,
                title=self.i18n.t(
                    "conversation_orchestrator",
                    (
                        "timeline.intents_added_title"
                        if intents_added > 0
                        else "timeline.no_intents_added_title"
                    ),
                    count=intents_added,
                    default=(
                        f"Added {intents_added} intent(s) to Mindscape"
                        if intents_added > 0
                        else "No new intents"
                    ),
                ),
                summary=self.i18n.t(
                    "conversation_orchestrator",
                    (
                        "timeline.intents_added_summary"
                        if intents_added > 0
                        else "timeline.all_intents_exist_summary"
                    ),
                    count=intents_added,
                    default=(
                        f"Added {intents_added} intent(s) from message"
                        if intents_added > 0
                        else "All intents already exist"
                    ),
                ),
                data={
                    "intents": intents,
                    "themes": themes,
                    "source": "intent_extraction_task",
                    "intents_added": intents_added,
                },
                cta=None,
                created_at=_utc_now(),
            )
            self.timeline_items_store.create_timeline_item(timeline_item)
            logger.info(f"Created TimelineItem for intent extraction: {timeline_item.id}")
            return timeline_item
        except Exception as exc:
            logger.error(
                f"Failed to create TimelineItem for extraction: {exc}",
                exc_info=True,
            )
            return None
