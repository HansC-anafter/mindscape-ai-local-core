"""
PlaybookPhaseManager - manages phase summaries and external memory integration

Provides phase summary creation and management for long-running playbook executions,
enabling context compression and external memory storage.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.app.services.stores.playbook_executions_store import PlaybookExecutionsStore
from backend.app.services.stores.events_store import EventsStore
from backend.app.models.mindscape import MindEvent, EventType, EventActor

logger = logging.getLogger(__name__)


class PlaybookPhaseManager:
    """
    Manages phase summaries for playbook executions

    Phase summaries capture the essence of completed phases and store them
    in external memory, enabling context compression for long-running executions.
    """

    def __init__(self, executions_store: PlaybookExecutionsStore, events_store: EventsStore):
        """
        Initialize phase manager

        Args:
            executions_store: Store for playbook executions
            events_store: Store for mind events
        """
        self.executions_store = executions_store
        self.events_store = events_store

    async def write_phase_summary(
        self,
        execution_id: str,
        phase_id: str,
        summary: str,
        artifacts: List[str],
        workspace_id: str,
        intent_instance_id: Optional[str] = None
    ) -> str:
        """
        Write phase summary to external memory

        Creates a PHASE_SUMMARY event and updates the execution record.

        Args:
            execution_id: Playbook execution ID
            phase_id: Phase identifier
            summary: Phase summary text
            artifacts: List of artifact IDs produced in this phase
            workspace_id: Workspace ID
            intent_instance_id: Optional intent instance ID

        Returns:
            Event ID of the created phase summary
        """
        # Create phase summary event
        event_payload = {
            "execution_id": execution_id,
            "phase_id": phase_id,
            "summary": summary,
            "artifacts": artifacts,
            "intent_instance_id": intent_instance_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        event = MindEvent(
            id=f"phase_summary_{execution_id}_{phase_id}_{int(datetime.utcnow().timestamp())}",
            timestamp=datetime.utcnow(),
            actor=EventActor.SYSTEM,
            channel="playbook",
            profile_id="",  # Will be set by caller
            workspace_id=workspace_id,
            project_id=None,
            event_type=EventType.PHASE_SUMMARY,
            payload=event_payload,
            metadata={
                "execution": {
                    "playbook_execution_id": execution_id
                },
                "intent": {
                    "intent_instance_id": intent_instance_id
                } if intent_instance_id else None
            }
        )

        # Store the event
        created_event = await self.events_store.create_event(event)

        # Update execution record with phase summary
        success = self.executions_store.add_phase_summary(
            execution_id=execution_id,
            phase=phase_id,
            summary_data={
                "phase_id": phase_id,
                "summary": summary,
                "artifacts": artifacts,
                "event_id": created_event.id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        if not success:
            logger.warning(f"Failed to update execution record for phase summary: {execution_id}")

        logger.info(f"Created phase summary event: {created_event.id} for execution: {execution_id}, phase: {phase_id}")
        return created_event.id

    async def load_phase_summaries(self, execution_id: str) -> List[Dict[str, Any]]:
        """
        Load phase summaries for an execution

        Args:
            execution_id: Playbook execution ID

        Returns:
            List of phase summary data
        """
        # Get phase summaries from MindEvents
        events = await self.events_store.get_events_by_type_and_metadata(
            event_type=EventType.PHASE_SUMMARY,
            metadata_filter={
                "execution.playbook_execution_id": execution_id
            }
        )

        phase_summaries = []
        for event in events:
            if hasattr(event, 'payload'):
                payload = event.payload
            elif isinstance(event, dict):
                payload = event.get("payload", {})
            else:
                continue

            phase_summaries.append({
                "phase_id": payload.get("phase_id"),
                "summary": payload.get("summary"),
                "artifacts": payload.get("artifacts", []),
                "timestamp": payload.get("timestamp"),
                "event_id": event.id if hasattr(event, 'id') else event.get("id")
            })

        # Sort by timestamp
        phase_summaries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        logger.info(f"Loaded {len(phase_summaries)} phase summaries for execution: {execution_id}")
        return phase_summaries

    async def get_phase_context(self, execution_id: str, max_phases: int = 5) -> str:
        """
        Get phase context for LLM consumption

        Combines recent phase summaries into a context string suitable
        for LLM input, enabling context compression.

        Args:
            execution_id: Playbook execution ID
            max_phases: Maximum number of recent phases to include

        Returns:
            Formatted context string
        """
        phase_summaries = await self.load_phase_summaries(execution_id)

        if not phase_summaries:
            return "No previous phases completed."

        # Take the most recent phases
        recent_phases = phase_summaries[:max_phases]

        context_parts = []
        for phase in recent_phases:
            context_parts.append(f"""
Phase: {phase['phase_id']}
Summary: {phase['summary']}
Artifacts: {', '.join(phase['artifacts']) if phase['artifacts'] else 'None'}
Completed: {phase['timestamp']}
""".strip())

        context = "\n\n".join(context_parts)

        logger.info(f"Generated phase context for execution: {execution_id} ({len(recent_phases)} phases)")
        return context

    async def get_latest_phase_summary(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent phase summary

        Args:
            execution_id: Playbook execution ID

        Returns:
            Latest phase summary data or None
        """
        phase_summaries = await self.load_phase_summaries(execution_id)
        return phase_summaries[0] if phase_summaries else None

    async def compress_context_if_needed(
        self,
        execution_id: str,
        current_context_length: int,
        max_context_length: int = 8000
    ) -> bool:
        """
        Check if context compression is needed and trigger if appropriate

        Args:
            execution_id: Playbook execution ID
            current_context_length: Current context length (approximate)
            max_context_length: Maximum allowed context length

        Returns:
            True if compression was triggered, False otherwise
        """
        if current_context_length <= max_context_length:
            return False

        # Get current execution
        execution = self.executions_store.get_execution(execution_id)
        if not execution:
            return False

        # Trigger phase summary creation for current phase
        # This is a signal that compression is needed
        logger.info(f"Context compression triggered for execution: {execution_id} "
                   f"(context length: {current_context_length})")

        # Note: Actual compression logic would be implemented in the playbook runner
        # This method just signals that compression is needed
        return True
