"""Surface Events store for data persistence."""
import logging
from datetime import datetime
from typing import List, Optional

from .base import StoreBase
from ...models.surface import SurfaceEvent

logger = logging.getLogger(__name__)


class SurfaceEventsStore(StoreBase):
    """Store for managing Surface Events."""

    def create_event(self, event: SurfaceEvent) -> SurfaceEvent:
        """
        Create a new event.

        Args:
            event: Event to create

        Returns:
            Created event
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO surface_events (
                    event_id, workspace_id, source_surface, event_type,
                    actor_id, payload, command_id, thread_id, correlation_id,
                    parent_event_id, execution_id, pack_id, card_id, scope,
                    playbook_version, timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.event_id,
                event.workspace_id,
                event.source_surface,
                event.event_type,
                event.actor_id,
                self.serialize_json(event.payload),
                event.command_id,
                event.thread_id,
                event.correlation_id,
                event.parent_event_id,
                event.execution_id,
                event.pack_id,
                event.card_id,
                event.scope,
                event.playbook_version,
                self.to_isoformat(event.timestamp or datetime.utcnow()),
                self.to_isoformat(event.created_at or datetime.utcnow())
            ))
            logger.info(f"Created Surface Event: {event.event_id}")
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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM surface_events WHERE workspace_id = ?'
            params = [workspace_id]

            if surface_filter:
                query += ' AND source_surface = ?'
                params.append(surface_filter)

            if event_type_filter:
                query += ' AND event_type = ?'
                params.append(event_type_filter)

            if actor_filter:
                query += ' AND actor_id = ?'
                params.append(actor_filter)

            if command_id_filter:
                query += ' AND command_id = ?'
                params.append(command_id_filter)

            if thread_id_filter:
                query += ' AND thread_id = ?'
                params.append(thread_id_filter)

            if correlation_id_filter:
                query += ' AND correlation_id = ?'
                params.append(correlation_id_filter)

            if pack_id_filter:
                query += ' AND pack_id = ?'
                params.append(pack_id_filter)

            if card_id_filter:
                query += ' AND card_id = ?'
                params.append(card_id_filter)

            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> SurfaceEvent:
        """Convert database row to SurfaceEvent."""
        return SurfaceEvent(
            event_id=row['event_id'],
            workspace_id=row['workspace_id'],
            source_surface=row['source_surface'],
            event_type=row['event_type'],
            actor_id=row['actor_id'],
            payload=self.deserialize_json(row['payload'], default={}),
            command_id=row['command_id'],
            thread_id=row['thread_id'],
            correlation_id=row['correlation_id'],
            parent_event_id=row['parent_event_id'],
            execution_id=row['execution_id'],
            pack_id=row.get('pack_id'),
            card_id=row.get('card_id'),
            scope=row.get('scope'),
            playbook_version=row.get('playbook_version'),
            timestamp=self.from_isoformat(row['timestamp']),
            created_at=self.from_isoformat(row['created_at'])
        )

