"""
Conversation History Module

Manages conversation history with sliding window and summary support.
"""

import logging
from typing import List, Any, Tuple, Optional

logger = logging.getLogger(__name__)


class ConversationHistoryManager:
    """Manages conversation history with sliding window and summary support"""

    def __init__(self, store: Any = None, summary_policy: Any = None):
        """
        Initialize ConversationHistoryManager

        Args:
            store: MindscapeStore instance
            summary_policy: SummaryPolicy instance for triggering summaries
        """
        self.store = store
        self.summary_policy = summary_policy

    async def get_conversation_history_with_summary(
        self,
        workspace_id: str,
        max_events: int,
        max_messages: int,
        max_chars: int,
        thread_id: Optional[str] = None,
    ) -> Tuple[List[str], Optional[str]]:
        """
        Get conversation history with sliding window and summary support

        Args:
            workspace_id: Workspace ID
            max_events: Maximum events to fetch
            max_messages: Maximum messages to return
            max_chars: Maximum characters per message
            thread_id: Optional thread ID for thread-scoped history

        Returns:
            Tuple of (recent_messages, summary_text)
        """
        try:
            if thread_id:
                recent_events = self.store.events.get_events_by_thread(
                    workspace_id=workspace_id, thread_id=thread_id, limit=max_events
                )
            else:
                recent_events = self.store.get_events_by_workspace(
                    workspace_id=workspace_id, limit=max_events
                )

            # Separate message events and summary events
            message_events = []
            summary_events = []

            for event in recent_events:
                if hasattr(event, "event_type"):
                    event_type = (
                        event.event_type.value
                        if hasattr(event.event_type, "value")
                        else str(event.event_type)
                    )
                    if event_type == "message":
                        message_events.append(event)
                    elif event_type == "summary" or event_type == "insight":
                        is_summary = False
                        if event_type == "summary":
                            is_summary = True
                        elif hasattr(event, "metadata") and isinstance(
                            event.metadata, dict
                        ):
                            is_summary = event.metadata.get("is_summary", False)

                        if is_summary:
                            summary_events.append(event)

            # Get most recent summary (if exists)
            summary_text = None
            if summary_events:
                latest_summary = summary_events[0]  # Assuming sorted by time
                payload = (
                    latest_summary.payload
                    if isinstance(latest_summary.payload, dict)
                    else {}
                )
                summary_text = payload.get("summary", "") or payload.get("content", "")
                if summary_text:
                    summary_text = summary_text[:1000]  # Limit summary length

            # Process message events
            conversation_context = []
            for event in message_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                msg = payload.get("message", "")
                actor = (
                    event.actor.value
                    if hasattr(event.actor, "value")
                    else str(event.actor)
                )
                if msg and actor in ["user", "assistant"]:
                    role = "User" if actor == "user" else "Assistant"
                    truncated_msg = msg[:max_chars] if len(msg) > max_chars else msg

                    # Filter out generic welcome/suggestion messages
                    if role == "Assistant":
                        if self._is_generic_message(truncated_msg):
                            logger.info(
                                f"Filtered out generic Assistant message: {truncated_msg[:200]}..."
                            )
                            continue

                    conversation_context.append(f"{role}: {truncated_msg}")

            # Apply sliding window: keep only most recent messages
            messages_to_keep = conversation_context[-max_messages:]

            # Check if summary should be triggered
            if self.summary_policy:
                should_summarize_flag, summary_reason = (
                    await self.summary_policy.should_summarize(
                        workspace_id=workspace_id,
                        conversation_context=conversation_context,
                        recent_events=recent_events,
                    )
                )

                if should_summarize_flag:
                    summary_threshold = min(30, max(int(max_messages * 0.3), 20))
                    messages_to_summarize = (
                        conversation_context[:-summary_threshold]
                        if len(conversation_context) > summary_threshold
                        else []
                    )

                    if len(messages_to_summarize) >= 5:
                        # Check if we already have a recent summary
                        summary_generated = False
                        if not summary_events or len(summary_events) == 0:
                            try:
                                await self.summary_policy.generate_and_store_summary(
                                    workspace_id=workspace_id,
                                    messages_to_summarize=messages_to_summarize,
                                    profile_id=getattr(self, "profile_id", None),
                                    summary_type=(
                                        "HISTORY_SUMMARY"
                                        if "capacity" in summary_reason.lower()
                                        else "EPISODE_SUMMARY"
                                    ),
                                )
                                summary_generated = True
                                logger.info(
                                    f"Auto-generated summary ({summary_reason}) for "
                                    f"{len(messages_to_summarize)} old messages"
                                )
                            except Exception as e:
                                logger.error(f"Failed to auto-generate summary: {e}")
                                raise

                        if summary_generated:
                            messages_to_keep = conversation_context[-summary_threshold:]
                            return messages_to_keep, summary_text

            return messages_to_keep, summary_text

        except Exception as e:
            logger.warning(f"Failed to get conversation history with summary: {e}")
            return [], None

    def _is_generic_message(self, message: str) -> bool:
        """
        Check if a message is a generic welcome/suggestion message

        Args:
            message: Message text to check

        Returns:
            True if message is generic and should be filtered
        """
        generic_patterns = [
            "I can help you:",
            "Execute Playbook workflows",
            "Quick start:",
            "Suggestion:",
            "If this is your first time",
            "Let me know what you need help with",
            "can help you:",
            "I can help you",
            "Quick start",
            "Suggestions",
        ]

        msg_lower = message.lower()
        has_generic = any(pattern.lower() in msg_lower for pattern in generic_patterns)

        if has_generic:
            # Calculate generic content ratio
            generic_chars = sum(
                len(p) for p in generic_patterns if p.lower() in msg_lower
            )
            total_chars = len(message)
            # Filter if more than 30% generic content OR if message is primarily generic
            if total_chars > 0 and (
                generic_chars > total_chars * 0.3 or generic_chars > 100
            ):
                return True

        return False
