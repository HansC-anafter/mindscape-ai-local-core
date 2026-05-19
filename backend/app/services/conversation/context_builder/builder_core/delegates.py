"""Compatibility delegates exposed by ContextBuilder."""

from typing import Any, List, Optional, Tuple


class ContextDelegatesMixin:
    """Delegate legacy helper methods to extracted collaborators."""

    def estimate_token_count(self, text: str, model_name: Optional[str] = None) -> int:
        """Delegate token counting to TokenEstimator."""
        return self.token_estimator.estimate(text, model_name)

    async def should_summarize(
        self,
        workspace_id: str,
        conversation_context: List[str],
        recent_events: List[Any],
    ) -> Tuple[bool, str]:
        """Delegate to SummaryPolicy."""
        return await self.summary_policy.should_summarize(
            workspace_id, conversation_context, recent_events
        )

    async def _get_conversation_history_with_summary(
        self,
        workspace_id: str,
        max_events: int,
        max_messages: int,
        max_chars: int,
        thread_id: Optional[str] = None,
    ) -> Tuple[List[str], Optional[str]]:
        """Delegate to ConversationHistoryManager."""
        return await self.conversation_history_manager.get_conversation_history_with_summary(
            workspace_id, max_events, max_messages, max_chars, thread_id
        )

    def _should_include_side_chain(
        self,
        side_chain_mode: str,
        thread_id: Optional[str],
        message: Optional[str],
        thread_context_count: int,
    ) -> bool:
        """Delegate to SideChainHandler."""
        return self.side_chain_handler.should_include_side_chain(
            side_chain_mode, thread_id, message, thread_context_count
        )

    def _build_workspace_side_chain_context(
        self, workspace_id: str, task_limit: int = 5, timeline_limit: int = 5
    ) -> List[str]:
        """Delegate to SideChainHandler."""
        return self.side_chain_handler.build_workspace_side_chain_context(
            workspace_id, task_limit, timeline_limit
        )

    async def _get_multi_scope_memory(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        intent_id: Optional[str] = None,
    ) -> Optional[str]:
        """Delegate to MemoryRetriever."""
        return await self.memory_retriever.get_multi_scope_memory(
            workspace_id, message, profile_id, intent_id
        )

    async def _get_long_term_memory_context(
        self, workspace_id: str, message: str, profile_id: Optional[str] = None
    ) -> Optional[str]:
        """Delegate to MemoryRetriever."""
        return await self.memory_retriever.get_long_term_memory_context(
            workspace_id, message, profile_id
        )

    async def _generate_and_store_summary(
        self,
        workspace_id: str,
        messages_to_summarize: List[str],
        profile_id: Optional[str] = None,
        summary_type: str = "HISTORY_SUMMARY",
    ):
        """Delegate to SummaryPolicy."""
        return await self.summary_policy.generate_and_store_summary(
            workspace_id, messages_to_summarize, profile_id, summary_type
        )

    def _calculate_capacity_score(self, conversation_context: List[str]) -> float:
        """Delegate to SummaryPolicy."""
        return self.summary_policy._calculate_capacity_score(conversation_context)

    async def _detect_episode_boundary(
        self, workspace_id: str, recent_events: List[Any]
    ) -> Tuple[float, str]:
        """Delegate to SummaryPolicy."""
        return await self.summary_policy._detect_episode_boundary(
            workspace_id, recent_events
        )

    async def _calculate_salience_score(
        self, conversation_context: List[str], recent_events: List[Any]
    ) -> float:
        """Delegate to SummaryPolicy."""
        return await self.summary_policy._calculate_salience_score(
            conversation_context, recent_events
        )
