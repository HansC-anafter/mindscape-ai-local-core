"""
Side Chain Handler Module

Handles workspace side-chain context building for cross-thread references.
"""

import logging
from typing import List, Optional, Any

logger = logging.getLogger(__name__)


class SideChainHandler:
    """Handles side-chain context building for workspace-wide references"""

    def __init__(self, store: Any = None, timeline_items_store: Any = None):
        """
        Initialize SideChainHandler

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
        """
        self.store = store
        self.timeline_items_store = timeline_items_store

    def should_include_side_chain(
        self,
        side_chain_mode: str,
        thread_id: Optional[str],
        message: Optional[str],
        thread_context_count: int,
    ) -> bool:
        """
        Determine if side-chain context should be included

        Args:
            side_chain_mode: Policy mode ("off", "auto", "force")
            thread_id: Current thread ID
            message: User message
            thread_context_count: Number of messages in thread context

        Returns:
            True if side-chain should be included
        """
        if side_chain_mode == "off" or not thread_id:
            return False

        if side_chain_mode == "force":
            return True

        message_text = message or ""
        message_lower = message_text.lower()

        en_triggers = [
            "other thread",
            "another thread",
            "previous thread",
            "earlier thread",
            "across threads",
            "cross-thread",
            "whole workspace",
            "entire workspace",
        ]
        zh_triggers = [
            "另一個",
            "另一條",
            "上一個",
            "前一個",
            "其他對話",
            "跨 thread",
            "跨對話",
            "整個工作區",
            "同一個工作區",
        ]

        if any(trigger in message_lower for trigger in en_triggers):
            return True
        if any(trigger in message_text for trigger in zh_triggers):
            return True

        return thread_context_count < 2

    def build_workspace_side_chain_context(
        self, workspace_id: str, task_limit: int = 5, timeline_limit: int = 5
    ) -> List[str]:
        """
        Build side-chain context from workspace-wide data

        Args:
            workspace_id: Workspace ID
            task_limit: Maximum number of tasks to include
            timeline_limit: Maximum number of timeline items to include

        Returns:
            List of context strings
        """
        side_chain_parts = []
        task_lines = []
        timeline_lines = []

        if self.store:
            try:
                from backend.app.services.stores.tasks_store import TasksStore

                tasks_store = TasksStore(self.store.db_path)

                running_tasks = tasks_store.list_running_tasks(workspace_id)
                pending_tasks = tasks_store.list_pending_tasks(workspace_id)

                for task in (running_tasks + pending_tasks)[:task_limit]:
                    task_status = (
                        task.status.value
                        if hasattr(task.status, "value")
                        else str(task.status)
                    )
                    task_info = f"- {task.pack_id} ({task_status})"
                    if task.task_type:
                        task_info += f": {task.task_type}"
                    task_lines.append(task_info)
            except Exception as e:
                logger.warning(f"Failed to build workspace side-chain tasks: {e}")

        if self.timeline_items_store:
            try:
                recent_timeline_items = (
                    self.timeline_items_store.list_timeline_items_by_workspace(
                        workspace_id=workspace_id, limit=timeline_limit
                    )
                )
                for item in recent_timeline_items[:timeline_limit]:
                    item_type = (
                        item.type.value
                        if hasattr(item.type, "value")
                        else str(item.type)
                    )
                    item_info = f"- {item_type}: {item.title}"
                    if item.summary:
                        item_info += f" - {item.summary[:120]}"
                    timeline_lines.append(item_info)
            except Exception as e:
                logger.warning(f"Failed to build workspace side-chain timeline: {e}")

        if not task_lines and not timeline_lines:
            return []

        side_chain_parts.append("\n## Workspace Side-Chain (Reference Only):")
        side_chain_parts.append(
            "Workspace-wide snapshot (may include other threads and legacy events). "
            "Use only when the user explicitly references other threads or when thread context is insufficient."
        )

        if task_lines:
            side_chain_parts.append("\nCross-Thread Tasks Snapshot:")
            side_chain_parts.extend(task_lines)

        if timeline_lines:
            side_chain_parts.append("\nCross-Thread Timeline Snapshot:")
            side_chain_parts.extend(timeline_lines)

        return side_chain_parts
