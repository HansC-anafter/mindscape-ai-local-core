"""
Task Events Emitter

Emits task events (created/updated) via callback with error handling.
"""

import logging
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class TaskEventsEmitter:
    """
    Emits task events via callback

    Responsibilities:
    - Emit task created/updated events
    - Format task event data
    - Handle callback errors gracefully
    """

    def __init__(
        self,
        callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize TaskEventsEmitter

        Args:
            callback: Optional task event callback function
        """
        self.callback = callback

    def emit_task_created(
        self,
        task_id: str,
        pack_id: str,
        status: str,
        task_type: str,
        workspace_id: str,
        playbook_code: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> None:
        """
        Emit task created event

        Args:
            task_id: Task ID
            pack_id: Pack ID
            status: Task status
            task_type: Task type
            workspace_id: Workspace ID
            playbook_code: Optional playbook code
            execution_id: Optional execution ID
        """
        event_data = self._format_task_event(
            task_id=task_id,
            pack_id=pack_id,
            status=status,
            task_type=task_type,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            execution_id=execution_id,
        )

        self._safe_emit("created", event_data)

    def emit_task_updated(
        self,
        task_id: str,
        pack_id: str,
        status: str,
        task_type: str,
        workspace_id: str,
    ) -> None:
        """
        Emit task updated event

        Args:
            task_id: Task ID
            pack_id: Pack ID
            status: Task status
            task_type: Task type
            workspace_id: Workspace ID
        """
        event_data = self._format_task_event(
            task_id=task_id,
            pack_id=pack_id,
            status=status,
            task_type=task_type,
            workspace_id=workspace_id,
        )

        self._safe_emit("updated", event_data)

    def _format_task_event(
        self,
        task_id: str,
        pack_id: str,
        status: str,
        task_type: str,
        workspace_id: str,
        playbook_code: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Format task event data

        Args:
            task_id: Task ID
            pack_id: Pack ID
            status: Task status
            task_type: Task type
            workspace_id: Workspace ID
            playbook_code: Optional playbook code
            execution_id: Optional execution ID

        Returns:
            Formatted event data dict
        """
        event_data = {
            "id": task_id,
            "pack_id": pack_id,
            "status": status,
            "task_type": task_type,
            "workspace_id": workspace_id,
        }

        if playbook_code:
            event_data["playbook_code"] = playbook_code

        if execution_id:
            event_data["execution_id"] = execution_id

        return event_data

    def _safe_emit(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Safely emit event via callback with error handling

        Args:
            event_type: Event type (created/updated)
            event_data: Event data dict
        """
        if not self.callback:
            return

        try:
            self.callback(event_type, event_data)
        except Exception as e:
            logger.warning(f"Failed to emit task event {event_type}: {e}")
