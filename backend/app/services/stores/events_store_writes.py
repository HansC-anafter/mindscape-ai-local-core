"""
Write operations for the legacy SQLite EventsStore.
"""

from typing import Optional, Dict, Any
import asyncio
import logging

from ...models.mindscape import MindEvent

logger = logging.getLogger(__name__)


class EventsStoreWriteMixin:
    """Write methods for EventsStore."""

    def create_event(self, event: MindEvent, generate_embedding: bool = False) -> MindEvent:
        """
        Create a new mindspace event

        Args:
            event: MindEvent to create
            generate_embedding: Whether to automatically generate embedding for this event

        Returns:
            Created MindEvent
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mind_events (
                    id, timestamp, actor, channel, profile_id, project_id, workspace_id,
                    thread_id, event_type, payload, entity_ids, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.id,
                self.to_isoformat(event.timestamp),
                event.actor.value,
                event.channel,
                event.profile_id,
                event.project_id,
                event.workspace_id,
                event.thread_id,
                event.event_type.value,
                self.serialize_json(event.payload),
                self.serialize_json(event.entity_ids),
                self.serialize_json(event.metadata)
            ))
            conn.commit()

        if generate_embedding:
            self._trigger_event_embedding_generation(event)

        return event

    def _trigger_event_embedding_generation(self, event: MindEvent) -> None:
        try:
            from backend.app.services.event_embedding_generator import EventEmbeddingGenerator

            generator = EventEmbeddingGenerator()
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(generator.generate_embedding_for_event(event))
                else:
                    asyncio.run(generator.generate_embedding_for_event(event))
            except RuntimeError:
                asyncio.run(generator.generate_embedding_for_event(event))
        except Exception as e:
            logger.warning(f"Failed to generate embedding for event {event.id}: {e}")

    def get_event(self, event_id: str) -> Optional[MindEvent]:
        """
        Get a single event by ID

        Args:
            event_id: Event ID

        Returns:
            MindEvent or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_events WHERE id = ?', (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
        return self._row_to_event(row)

    def update_event(
        self,
        event_id: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update event payload and/or metadata

        Args:
            event_id: Event ID
            payload: New payload (if provided)
            metadata: New metadata (if provided)

        Returns:
            True if update succeeded
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            updates = []
            values = []

            if payload is not None:
                updates.append('payload = ?')
                values.append(self.serialize_json(payload))

            if metadata is not None:
                updates.append('metadata = ?')
                values.append(self.serialize_json(metadata))

            if not updates:
                return True

            values.append(event_id)

            cursor.execute(
                f'UPDATE mind_events SET {", ".join(updates)} WHERE id = ?',
                values
            )

            conn.commit()
            return cursor.rowcount > 0
