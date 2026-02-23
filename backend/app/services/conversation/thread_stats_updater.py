"""
Thread Statistics Updater

Encapsulates the duplicated thread message-count and last-message-at
update pattern used in both the PipelineCore shim path and the legacy
routing path.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def update_thread_stats(store, workspace_id: str, thread_id: str) -> None:
    """
    Update thread message count and last_message_at timestamp.

    Counts messages via the events store and persists the updated
    statistics on the conversation thread record.

    Args:
        store: MindscapeStore instance (must expose .events and .conversation_threads).
        workspace_id: Workspace that owns the thread.
        thread_id: Conversation thread to update.
    """
    if not thread_id:
        return

    try:
        message_count = store.events.count_messages_by_thread(
            workspace_id=workspace_id, thread_id=thread_id
        )
        store.conversation_threads.update_thread(
            thread_id=thread_id,
            last_message_at=_utc_now(),
            message_count=message_count,
        )
    except Exception as e:
        logger.warning("Failed to update thread statistics: %s", e)
