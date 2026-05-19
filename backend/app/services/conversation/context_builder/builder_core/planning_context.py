"""Planning context assembly for ContextBuilder."""

import logging
from typing import Any, Optional

from ..tool_context import build_tool_context_section

logger = logging.getLogger(__name__)


class PlanningContextMixin:
    """Build structured context for planning tasks."""

    async def build_planning_context(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        target_tokens: Optional[int] = None,
        mode: str = "planning",
        thread_id: Optional[str] = None,
        side_chain_mode: str = "off",
    ) -> str:
        """
        Build structured context specifically for planning tasks.

        Args:
            workspace_id: Workspace ID.
            message: User message.
            profile_id: Optional profile ID for retrieving intents.
            workspace: Optional workspace object for metadata.
            target_tokens: Target token budget for the context.
            mode: Context mode.
            thread_id: Optional thread ID for thread-scoped context.
            side_chain_mode: Side-chain policy.

        Returns:
            Structured context string optimized for planning tasks.
        """
        context_parts = []

        if target_tokens is None:
            model_max_tokens = 16385
            if hasattr(self, "model_name") and self.model_name:
                from backend.app.services.model_context_presets import (
                    get_context_preset,
                )

                try:
                    model_preset = get_context_preset(self.model_name)
                    model_max_tokens = model_preset.get(
                        "MAX_CONTEXT_TOKENS", model_max_tokens
                    )
                except Exception:
                    pass
            target_tokens = int(model_max_tokens * 0.6)

        logger.info(
            f"Building planning context with target_tokens={target_tokens}, mode={mode}"
        )

        workspace_profile = []
        if workspace:
            if workspace.title:
                workspace_profile.append(f"Title: {workspace.title}")
            if workspace.description:
                workspace_profile.append(f"Description: {workspace.description}")
            if workspace.mode:
                workspace_profile.append(f"Mode: {workspace.mode}")

        active_intents_summary = []
        if profile_id and self.store:
            try:
                from backend.app.models.mindscape import IntentStatus

                active_intents = self.store.list_intents(
                    profile_id=profile_id, status=IntentStatus.ACTIVE
                )
                if active_intents:
                    for intent in active_intents[:5]:
                        intent_summary = f"- {intent.title}"
                        if intent.description:
                            intent_summary += f": {intent.description[:100]}"
                        active_intents_summary.append(intent_summary)
            except Exception as e:
                logger.warning(f"Failed to get active intents: {e}")

        if workspace_profile or active_intents_summary:
            context_parts.append("## Workspace Profile")
            if workspace_profile:
                context_parts.extend(workspace_profile)
            if active_intents_summary:
                context_parts.append("\nKey Long-term Intents:")
                context_parts.extend(active_intents_summary)

        conversation_budget = int(target_tokens * 0.4)
        max_events = self.preset["MAX_EVENTS_FOR_QUERY"]
        max_messages = self.preset["MAX_HISTORY_MESSAGES"]
        max_chars = self.preset["MAX_MESSAGE_CHARS"]

        thread_context_count = 0
        try:
            if self.store:
                conversation_context, summary_context = (
                    await self.conversation_history_manager.get_conversation_history_with_summary(
                        workspace_id=workspace_id,
                        max_events=max_events,
                        max_messages=max_messages,
                        max_chars=max_chars,
                        thread_id=thread_id,
                    )
                )

                if summary_context:
                    context_parts.append("\n## Conversation Summary (Earlier Context):")
                    context_parts.append(summary_context)

                if conversation_context:
                    context_parts.append(
                        "\n## Recent Conversation (last N turns, compressed):"
                    )
                    messages_to_include = []
                    current_tokens = 0
                    for msg in reversed(conversation_context):
                        msg_tokens = self.estimate_token_count(msg, model_name=None)
                        if current_tokens + msg_tokens <= conversation_budget:
                            messages_to_include.insert(0, msg)
                            current_tokens += msg_tokens
                        else:
                            break
                    context_parts.extend(messages_to_include)
                    thread_context_count = len(messages_to_include)
                    logger.info(
                        f"Included {len(messages_to_include)} messages ({current_tokens} tokens) for planning"
                    )
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}", exc_info=True)

        active_packs_info = []
        if self.store:
            try:
                from backend.app.services.stores.tasks_store import TasksStore

                tasks_store = TasksStore()

                if thread_id:
                    running_tasks = tasks_store.list_running_tasks_by_thread(
                        workspace_id, thread_id
                    )
                    pending_tasks = tasks_store.list_pending_tasks_by_thread(
                        workspace_id, thread_id
                    )
                else:
                    running_tasks = tasks_store.list_running_tasks(workspace_id)
                    pending_tasks = tasks_store.list_pending_tasks(workspace_id)

                packs_state = {}
                for task in (running_tasks + pending_tasks)[:10]:
                    pack_id = task.pack_id if hasattr(task, "pack_id") else None
                    if pack_id:
                        if pack_id not in packs_state:
                            packs_state[pack_id] = []
                        status = (
                            task.status.value
                            if hasattr(task.status, "value")
                            else str(task.status)
                        )
                        packs_state[pack_id].append(status)

                if packs_state:
                    context_parts.append("\n## Active Packs & Their State:")
                    for pack_id, states in list(packs_state.items())[:5]:
                        state_summary = ", ".join(set(states))
                        active_packs_info.append(f"- {pack_id}: {state_summary}")
                    context_parts.extend(active_packs_info)
            except Exception as e:
                logger.warning(f"Failed to get active packs state: {e}")

        timeline_summary = []
        try:
            if self.timeline_items_store:
                if thread_id:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_thread(
                            workspace_id=workspace_id, thread_id=thread_id, limit=10
                        )
                    )
                else:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_workspace(
                            workspace_id=workspace_id, limit=10
                        )
                    )
                if recent_timeline_items:
                    for item in recent_timeline_items[:5]:
                        item_type = (
                            item.type.value
                            if hasattr(item.type, "value")
                            else str(item.type)
                        )
                        item_info = f"- {item_type}: {item.title}"
                        if item.summary:
                            item_info += f" - {item.summary[:100]}"
                        timeline_summary.append(item_info)
                    if timeline_summary:
                        context_parts.append("\n## Recent Timeline Activity (top 5):")
                        context_parts.extend(timeline_summary)
        except Exception as e:
            logger.warning(f"Failed to get timeline context: {e}")

        try:
            if self.side_chain_handler.should_include_side_chain(
                side_chain_mode=side_chain_mode,
                thread_id=thread_id,
                message=message,
                thread_context_count=thread_context_count,
            ):
                side_chain_parts = (
                    self.side_chain_handler.build_workspace_side_chain_context(
                        workspace_id=workspace_id
                    )
                )
                if side_chain_parts:
                    context_parts.extend(side_chain_parts)
                    logger.info("Injected workspace side-chain into planning context")
        except Exception as e:
            logger.warning(
                f"Failed to build workspace side-chain for planning context: {e}"
            )

        context_parts.extend(
            await build_tool_context_section(
                message=message,
                workspace_id=workspace_id,
            )
        )

        planning_context = "\n".join(context_parts) if context_parts else ""

        final_tokens = self.estimate_token_count(planning_context, model_name=None)
        logger.info(
            f"Built planning context: {final_tokens} tokens (target: {target_tokens})"
        )

        return planning_context
