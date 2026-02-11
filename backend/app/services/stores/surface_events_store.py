"""Surface Events store for data persistence (Postgres)."""
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from ...models.surface import SurfaceEvent

logger = logging.getLogger(__name__)


class SurfaceEventsStore(PostgresStoreBase):
    """Store for managing Surface Events (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_event(self, event: SurfaceEvent) -> SurfaceEvent:
        """Create a new event."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO surface_events (
                        event_id, workspace_id, source_surface, event_type,
                        actor_id, payload, command_id, thread_id, correlation_id,
                        parent_event_id, execution_id, pack_id, card_id, scope,
                        playbook_version, timestamp, created_at
                    ) VALUES (
                        :event_id, :workspace_id, :source_surface, :event_type,
                        :actor_id, :payload, :command_id, :thread_id, :correlation_id,
                        :parent_event_id, :execution_id, :pack_id, :card_id, :scope,
                        :playbook_version, :timestamp, :created_at
                    )
                """
                ),
                {
                    "event_id": event.event_id,
                    "workspace_id": event.workspace_id,
                    "source_surface": event.source_surface,
                    "event_type": event.event_type,
                    "actor_id": event.actor_id,
                    "payload": self.serialize_json(event.payload),
                    "command_id": event.command_id,
                    "thread_id": event.thread_id,
                    "correlation_id": event.correlation_id,
                    "parent_event_id": event.parent_event_id,
                    "execution_id": event.execution_id,
                    "pack_id": event.pack_id,
                    "card_id": event.card_id,
                    "scope": event.scope,
                    "playbook_version": event.playbook_version,
                    "timestamp": event.timestamp or _utc_now(),
                    "created_at": event.created_at or _utc_now(),
                },
            )
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
        limit: int = 50,
    ) -> List[SurfaceEvent]:
        """Get events with filters."""
        with self.get_connection() as conn:
            query = "SELECT * FROM surface_events WHERE workspace_id = :workspace_id"
            params = {"workspace_id": workspace_id, "limit": limit}

            if surface_filter:
                query += " AND source_surface = :source_surface"
                params["source_surface"] = surface_filter

            if event_type_filter:
                query += " AND event_type = :event_type"
                params["event_type"] = event_type_filter

            if actor_filter:
                query += " AND actor_id = :actor_id"
                params["actor_id"] = actor_filter

            if command_id_filter:
                query += " AND command_id = :command_id"
                params["command_id"] = command_id_filter

            if thread_id_filter:
                query += " AND thread_id = :thread_id"
                params["thread_id"] = thread_id_filter

            if correlation_id_filter:
                query += " AND correlation_id = :correlation_id"
                params["correlation_id"] = correlation_id_filter

            if pack_id_filter:
                query += " AND pack_id = :pack_id"
                params["pack_id"] = pack_id_filter

            if card_id_filter:
                query += " AND card_id = :card_id"
                params["card_id"] = card_id_filter

            query += " ORDER BY created_at DESC LIMIT :limit"

            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> SurfaceEvent:
        """Convert database row to SurfaceEvent."""
        data = row._mapping if hasattr(row, "_mapping") else row
        return SurfaceEvent(
            event_id=data["event_id"],
            workspace_id=data["workspace_id"],
            source_surface=data["source_surface"],
            event_type=data["event_type"],
            actor_id=data["actor_id"],
            payload=self.deserialize_json(data["payload"], default={}),
            command_id=data["command_id"],
            thread_id=data["thread_id"],
            correlation_id=data["correlation_id"],
            parent_event_id=data["parent_event_id"],
            execution_id=data["execution_id"],
            pack_id=data["pack_id"],
            card_id=data["card_id"],
            scope=data["scope"],
            playbook_version=data["playbook_version"],
            timestamp=data["timestamp"],
            created_at=data["created_at"],
        )
