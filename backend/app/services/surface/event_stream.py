"""Event Stream service for Surface events."""
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from ...models.surface import SurfaceEvent
from ...services.stores.surface_events_store import SurfaceEventsStore

logger = logging.getLogger(__name__)


class EventStreamService:
    """Service for managing Surface event stream."""

    def __init__(self, db_path: str = None):
        """
        Initialize event stream service.

        Args:
            db_path: Optional database path (defaults to standard location)
        """
        self.store = SurfaceEventsStore()

    def collect_event(
        self,
        workspace_id: str,
        source_surface: str,
        event_type: str,
        payload: Dict[str, Any],
        actor_id: Optional[str] = None,
        command_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        parent_event_id: Optional[str] = None,
        execution_id: Optional[str] = None
    ) -> SurfaceEvent:
        """
        Collect an event from any surface.

        Args:
            workspace_id: Workspace ID
            source_surface: Source surface ID
            event_type: Event type
            payload: Event payload
            actor_id: Optional actor ID
            command_id: Optional associated command ID

        Returns:
            Created event
        """
        import uuid

        # Extract BYOP/BYOL fields from payload and flatten to event fields
        byop_fields = ["pack_id", "card_id", "scope", "playbook_version"]
        byop_data = {}
        for field in byop_fields:
            if field in payload:
                value = payload[field]
                # Handle scope as list -> string conversion
                if field == "scope" and isinstance(value, list):
                    byop_data[field] = json.dumps(value) if value else None
                else:
                    byop_data[field] = str(value) if value is not None else None

        event = SurfaceEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            source_surface=source_surface,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
            command_id=command_id,
            thread_id=thread_id,
            correlation_id=correlation_id,
            parent_event_id=parent_event_id,
            execution_id=execution_id,
            pack_id=byop_data.get("pack_id"),
            card_id=byop_data.get("card_id"),
            scope=byop_data.get("scope"),
            playbook_version=byop_data.get("playbook_version"),
            timestamp=datetime.utcnow(),
            created_at=datetime.utcnow()
        )

        self.store.create_event(event)
        logger.info(f"Collected event {event.event_id} from {source_surface}")
        return event

    def get_events(
        self,
        workspace_id: str,
        surface_filter: Optional[str] = None,
        event_type_filter: Optional[str] = None,
        actor_filter: Optional[str] = None,
        command_id_filter: Optional[str] = None,
        thread_id_filter: Optional[str] = None,
        correlation_id_filter: Optional[str] = None,
        pack_id_filter: Optional[str] = None,
        card_id_filter: Optional[str] = None,
        limit: int = 50
    ) -> List[SurfaceEvent]:
        """
        Get events with filters.

        Args:
            workspace_id: Workspace ID
            surface_filter: Optional surface filter
            event_type_filter: Optional event type filter
            actor_filter: Optional actor filter
            command_id_filter: Optional command ID filter
            thread_id_filter: Optional thread ID filter
            correlation_id_filter: Optional correlation ID filter
            pack_id_filter: Optional pack ID filter (BYOP)
            card_id_filter: Optional card ID filter (BYOP)
            limit: Maximum number of results

        Returns:
            List of filtered events
        """
        return self.store.get_events(
            workspace_id=workspace_id,
            surface_filter=surface_filter,
            event_type_filter=event_type_filter,
            actor_filter=actor_filter,
            command_id_filter=command_id_filter,
            thread_id_filter=thread_id_filter,
            correlation_id_filter=correlation_id_filter,
            pack_id_filter=pack_id_filter,
            card_id_filter=card_id_filter,
            limit=limit
        )
