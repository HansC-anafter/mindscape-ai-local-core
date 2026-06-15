from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import (
    AgentExecution,
    Entity,
    EntityTag,
    EntityType,
    EventActor,
    EventType,
    IntentCard,
    IntentLog,
    IntentStatus,
    MindEvent,
    MindscapeProfile,
    PriorityLevel,
    Tag,
    TagCategory,
)
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store_utils import _utc_now


class MindscapeStoreEventMixin:
    def create_event(
        self, event: MindEvent, generate_embedding: bool = False
    ) -> MindEvent:
        """
        Create a new mindspace event

        Args:
            event: MindEvent to create
            generate_embedding: Whether to generate embedding for this event

        Returns:
            Created MindEvent
        """
        return self.events.create_event(event, generate_embedding=generate_embedding)

    def get_event(self, event_id: str) -> Optional[MindEvent]:
        """
        Get a single event by ID

        Args:
            event_id: Event ID

        Returns:
            MindEvent or None if not found
        """
        return self.events.get_event(event_id)

    def update_event(
        self,
        event_id: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update event payload and/or metadata

        Args:
            event_id: Event ID
            payload: New payload (optional)
            metadata: New metadata (optional)

        Returns:
            True if update succeeded
        """
        return self.events.update_event(event_id, payload=payload, metadata=metadata)

    def get_events(
        self,
        profile_id: str,
        event_type: Optional[EventType] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MindEvent]:
        """
        Get events for a profile with optional filters

        Args:
            profile_id: Profile ID
            event_type: Optional event type filter
            project_id: Optional project ID filter
            workspace_id: Optional workspace ID filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return

        Returns:
            List of MindEvent objects, ordered by timestamp DESC
        """
        return self.events.get_events(
            profile_id=profile_id,
            event_type=event_type,
            project_id=project_id,
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def get_events_by_project(
        self,
        project_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MindEvent]:
        """
        Get all events for a specific project

        Args:
            project_id: Project ID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return

        Returns:
            List of MindEvent objects for the project, ordered by timestamp DESC
        """
        return self.events.get_events_by_project(
            project_id, start_time=start_time, end_time=end_time, limit=limit
        )

    def get_events_by_workspace(
        self,
        workspace_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None,
    ) -> List[MindEvent]:
        """
        Get all events for a specific workspace

        Args:
            workspace_id: Workspace ID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return
            before_id: Optional event ID for cursor-based pagination

        Returns:
            List of MindEvent objects for the workspace, ordered by timestamp DESC
        """
        return self.events.get_events_by_workspace(
            workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            before_id=before_id,
        )

    def get_events_by_meeting_session(
        self,
        meeting_session_id: str,
        workspace_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[MindEvent]:
        """
        Get events for one meeting session.

        Reads meeting_session_id from event metadata or payload.
        """
        return self.events.get_events_by_meeting_session(
            meeting_session_id=meeting_session_id,
            workspace_id=workspace_id,
            limit=limit,
        )

    def get_timeline(
        self,
        profile_id: str,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 200,
    ) -> List[MindEvent]:
        """
        Get timeline events (for A.3: Mindspace viewer)

        This method supports the timeline viewer by providing flexible filtering
        and ordering. Events are returned in chronological order (oldest first).

        Args:
            profile_id: Profile ID
            project_id: Optional project filter
            workspace_id: Optional workspace filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            event_types: Optional list of event types to include
            limit: Maximum number of events

        Returns:
            List of MindEvent objects, ordered by timestamp ASC (for timeline display)
        """
        return self.events.get_timeline(
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            limit=limit,
        )
