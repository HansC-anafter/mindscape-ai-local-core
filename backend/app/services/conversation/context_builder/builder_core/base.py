"""Shared initialization for context builder composition."""

import logging
from typing import Optional

from backend.app.services.model_context_presets import get_context_preset

from ..conversation_history import ConversationHistoryManager
from ..memory_retriever import MemoryRetriever
from ..side_chain_handler import SideChainHandler
from ..summary_policy import SummaryPolicy
from ..token_estimator import TokenEstimator

logger = logging.getLogger(__name__)


class ContextBuilderBase:
    """Initialize shared dependencies for context builder mixins."""

    def __init__(
        self, store=None, timeline_items_store=None, model_name: Optional[str] = None
    ):
        """
        Initialize ContextBuilder.

        Args:
            store: MindscapeStore instance.
            timeline_items_store: TimelineItemsStore instance.
            model_name: Model name for context preset selection.
        """
        self.store = store
        self.timeline_items_store = timeline_items_store

        if not model_name or model_name.strip() == "":
            raise ValueError(
                "model_name is required for ContextBuilder. "
                "Please get the model name from SystemSettingsStore and pass it explicitly."
            )

        self.model_name = model_name
        self.preset = get_context_preset(model_name)

        self.token_estimator = TokenEstimator(model_name=model_name)
        self.summary_policy = SummaryPolicy(store=store, model_name=model_name)
        self.memory_retriever = MemoryRetriever(store=store)
        self.conversation_history_manager = ConversationHistoryManager(
            store=store, summary_policy=self.summary_policy
        )
        self.side_chain_handler = SideChainHandler(
            store=store, timeline_items_store=timeline_items_store
        )

        from backend.app.services.governance.memory_packet_compiler import (
            MemoryPacketCompiler,
        )

        self.memory_packet_compiler = MemoryPacketCompiler()

        logger.info(
            f"ContextBuilder initialized with model: {model_name or 'default'}, "
            f"preset: MAX_EVENTS={self.preset['MAX_EVENTS_FOR_QUERY']}, "
            f"MAX_MESSAGES={self.preset['MAX_HISTORY_MESSAGES']}, "
            f"MAX_CHARS={self.preset['MAX_MESSAGE_CHARS']}"
        )
