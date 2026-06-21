"""
Intent Infrastructure Service.

Local Mindscape Intent Runtime (L0) - Workspace Intent Bridge.

This service handles the bridge between Intent Governance Layer and Memory Layer,
specifically for converting intent candidates from LLM extraction into IntentCards
and TimelineItems in the local workspace.
"""

import logging
from typing import Any, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.intent_infra_core import (
    IntentCardsMixin,
    ProjectIntentMixin,
    SemanticSyncMixin,
    TimelineCreationMixin,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.postgres.timeline_items_store import (
    PostgresTimelineItemsStore,
)

logger = logging.getLogger(__name__)


class IntentInfraService(
    IntentCardsMixin,
    TimelineCreationMixin,
    ProjectIntentMixin,
    SemanticSyncMixin,
):
    """
    Local Mindscape Intent Infrastructure Service (L0).

    Responsibilities:
    - Convert intent candidates from LLM extraction to IntentCards
    - Create TimelineItems for intent extraction activities
    - Provide workspace-level intent management
    - Bridge to semantic-hub Intent Infra when available
    """

    def __init__(
        self,
        store: MindscapeStore,
        default_locale: str = "zh-TW",
        semantic_backend: Optional[Any] = None,
    ):
        """
        Initialize Intent Infrastructure Service.

        Args:
            store: MindscapeStore instance
            default_locale: Default locale for i18n
            semantic_backend: Optional semantic-hub backend
        """
        self.store = store
        self.default_locale = default_locale
        self.semantic_backend = semantic_backend
        self.timeline_items_store = PostgresTimelineItemsStore()
        self.i18n = get_i18n_service(default_locale=default_locale)

    async def handle_extraction_task(
        self,
        ctx: LocalDomainContext,
        task: Any,
        original_message_id: str,
    ) -> Dict[str, Any]:
        """
        Handle intent_extraction task execution.

        Args:
            ctx: Execution context
            task: Task record containing intents/themes in params
            original_message_id: Original message/event ID

        Returns:
            Result dict with pack_id and intents_added count
        """
        if not task:
            logger.warning("handle_extraction_task called without task")
            return {"pack_id": "intent_extraction", "intents_added": 0}

        intents = task.params.get("intents", []) if task.params else []
        themes = task.params.get("themes", []) if task.params else []

        if not intents:
            logger.info(f"No intents to process for task {task.id}")
            return {"pack_id": "intent_extraction", "intents_added": 0}

        intents_added = await self._create_intent_cards_from_candidates(
            ctx=ctx,
            intent_candidates=intents,
            task_id=task.id,
            workspace_id=ctx.workspace_id,
        )

        project_id = None
        if intents_added > 0 and intents:
            project_id = await self._create_project_from_intent(
                ctx=ctx,
                intent_candidates=intents,
                workspace_id=ctx.workspace_id,
            )

        timeline_item = await self._create_timeline_for_extraction(
            ctx=ctx,
            original_message_id=original_message_id,
            task_id=task.id,
            intents=intents,
            themes=themes,
            intents_added=intents_added,
        )

        if self.semantic_backend:
            await self._sync_to_semantic_hub(ctx=ctx, intents=intents, themes=themes)

        return {
            "pack_id": "intent_extraction",
            "intents_added": intents_added,
            "timeline_item_id": timeline_item.id if timeline_item else None,
            "project_id": project_id,
        }
