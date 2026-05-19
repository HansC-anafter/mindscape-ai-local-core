"""
Intent Extractor Service

Handles LLM-based intent extraction from user messages with context.
Creates TimelineItem (type=INTENT_SEEDS) for extracted intents/themes.
"""

import logging
from typing import Any, Dict, List, Optional

from ...core.domain_context import LocalDomainContext
from ...core.ports.intent_registry_port import IntentRegistryPort
from ...models.mindscape import IntentSource, IntentTag, IntentTagStatus
from ...models.workspace import TimelineItem, TimelineItemType
from ...services.i18n_service import get_i18n_service
from ...services.mindscape_store import MindscapeStore
from ...services.stores.intent_tags_store import IntentTagsStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...shared.llm_provider_helper import get_model_name_from_chat_model
from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.services.conversation.intent_extractor_core.clock import (
    utc_now as _utc_now,
)
from backend.app.services.conversation.intent_extractor_core.metadata import (
    update_event_metadata as update_event_metadata_core,
)
from backend.app.services.conversation.intent_extractor_core.runtime import (
    extract_and_create_timeline_item,
)
from backend.app.services.conversation.pack_suggester import PackSuggester
from backend.app.services.pack_info_collector import PackInfoCollector

logger = logging.getLogger(__name__)


class IntentExtractor:
    """
    Intent Extractor - extracts intents/themes using IntentRegistryPort and creates timeline items.

    Responsibilities:
    - Build context from recent files and timeline items
    - Extract intents/themes using IntentRegistryPort
    - Create TimelineItem (type=INTENT_SEEDS) for results
    - Update event metadata with extracted intents/themes
    """

    def __init__(
        self,
        store: MindscapeStore,
        timeline_items_store: TimelineItemsStore,
        intent_registry: IntentRegistryPort,
        default_locale: str = "en",
    ):
        """
        Initialize Intent Extractor.

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
            intent_registry: IntentRegistryPort instance
            default_locale: Default locale for i18n
        """
        self.store = store
        self.timeline_items_store = timeline_items_store
        self.default_locale = default_locale
        self.i18n = get_i18n_service(default_locale=default_locale)

        self.intent_registry = intent_registry
        self.intent_tags_store = IntentTagsStore()

        model_name = get_model_name_from_chat_model()
        if not model_name:
            raise ValueError("LLM model not configured in model-routing-registry.")
        if not model_name or model_name.strip() == "":
            raise ValueError(
                "LLM model is empty. Configure chat_model in model-routing-registry."
            )

        self.context_builder = ContextBuilder(
            store=store,
            timeline_items_store=timeline_items_store,
            model_name=model_name,
        )
        self.pack_suggester = PackSuggester()
        self.pack_info_collector = PackInfoCollector(db_path=store.db_path)

    async def extract_and_create_timeline_item(
        self,
        ctx: LocalDomainContext,
        message: str,
        message_id: str,
        locale: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Optional[TimelineItem]:
        """
        Extract intents/themes from message and create timeline item.

        Args:
            ctx: Execution context
            message: User message text
            message_id: Message/event ID
            locale: Target locale (optional)
            thread_id: Thread ID for conversation tracking (optional)

        Returns:
            Created TimelineItem or None if extraction failed or disabled
        """
        return await extract_and_create_timeline_item(
            extractor=self,
            ctx=ctx,
            message=message,
            message_id=message_id,
            locale=locale,
            thread_id=thread_id,
        )

    async def update_event_metadata(
        self, event_id: str, intents: List[Dict[str, Any]], themes: List[str]
    ) -> bool:
        """
        Update event metadata with extracted intents/themes.

        Args:
            event_id: Event ID
            intents: List of intent dicts with title/summary
            themes: List of theme strings

        Returns:
            True if update succeeded, False otherwise
        """
        return await update_event_metadata_core(
            store=self.store,
            event_id=event_id,
            intents=intents,
            themes=themes,
        )

    def confirm_intent(self, intent_tag_id: str) -> bool:
        """
        Confirm an intent tag (candidate -> confirmed).

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            True if confirmation succeeded
        """
        return self.intent_tags_store.confirm_intent(intent_tag_id)

    def reject_intent(self, intent_tag_id: str) -> bool:
        """
        Reject an intent tag (candidate -> rejected).

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            True if rejection succeeded
        """
        return self.intent_tags_store.reject_intent(intent_tag_id)

    def extract_intents(
        self, workspace_id: str, profile_id: str, message: str, message_id: str
    ) -> List[IntentTag]:
        """
        Extract intents and return candidate IntentTags.

        DEPRECATED: Use extract_intents_with_ctx() instead.

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message: User message text
            message_id: Message/event ID

        Returns:
            List of candidate IntentTags
        """
        ctx = LocalDomainContext(
            actor_id=profile_id, workspace_id=workspace_id, tags={"mode": "local"}
        )
        return self.extract_intents_with_ctx(
            ctx=ctx, message=message, message_id=message_id
        )

    def extract_intents_with_ctx(
        self, ctx: LocalDomainContext, message: str, message_id: str
    ) -> List[IntentTag]:
        """
        Extract intents and return candidate IntentTags using ExecutionContext.

        Args:
            ctx: Execution context
            message: User message text
            message_id: Message/event ID

        Returns:
            List of candidate IntentTags
        """
        return self.intent_tags_store.list_intent_tags(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            status=IntentTagStatus.CANDIDATE,
            limit=10,
        )
