from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import text
from app.services.stores.postgres_base import PostgresStoreBase
from app.models.mindscape import MindEvent, EventType, EventActor
import logging
import asyncio

logger = logging.getLogger(__name__)


class PostgresEventsStore(PostgresStoreBase):
    """Postgres implementation of EventsStore."""

    def create_event(
        self, event: MindEvent, generate_embedding: bool = False
    ) -> MindEvent:
        """Create a new mindspace event"""
        query = text(
            """
            INSERT INTO mind_events (
                id, timestamp, actor, channel, profile_id, project_id, workspace_id,
                thread_id, event_type, payload, entity_ids, metadata
            ) VALUES (
                :id, :timestamp, :actor, :channel, :profile_id, :project_id, :workspace_id,
                :thread_id, :event_type, :payload, :entity_ids, :metadata
            )
        """
        )
        params = {
            "id": event.id,
            "timestamp": event.timestamp,
            "actor": event.actor.value,
            "channel": event.channel,
            "profile_id": event.profile_id,
            "project_id": event.project_id,
            "workspace_id": event.workspace_id,
            "thread_id": event.thread_id,
            "event_type": event.event_type.value,
            "payload": self.serialize_json(event.payload),
            "entity_ids": self.serialize_json(event.entity_ids),
            "metadata": self.serialize_json(event.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)

        # Generate embedding asynchronously (mirrors legacy behavior)
        if generate_embedding:
            self._trigger_embedding_generation(event)

        return event

    def _trigger_embedding_generation(self, event: MindEvent):
        """Trigger async embedding generation safely"""
        try:
            from app.services.event_embedding_generator import EventEmbeddingGenerator

            generator = EventEmbeddingGenerator()
            # Fire and forget
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(generator.generate_embedding_for_event(event))
                else:
                    asyncio.run(generator.generate_embedding_for_event(event))
            except RuntimeError:
                asyncio.run(generator.generate_embedding_for_event(event))
        except Exception as e:
            logger.warning(f"Failed to trigger embedding for event {event.id}: {e}")

    def get_event(self, event_id: str) -> Optional[MindEvent]:
        """Get a single event by ID"""
        query = text("SELECT * FROM mind_events WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": event_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_event(row)

    def update_event(
        self,
        event_id: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update event payload and/or metadata"""
        updates = []
        params = {"id": event_id}

        if payload is not None:
            updates.append("payload = :payload")
            params["payload"] = self.serialize_json(payload)

        if metadata is not None:
            updates.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(metadata)

        if not updates:
            return True

        query = text(f"UPDATE mind_events SET {', '.join(updates)} WHERE id = :id")
        with self.transaction() as conn:
            result = conn.execute(query, params)
            return result.rowcount > 0

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
        """Get events for a profile with filters"""
        base_query = "SELECT * FROM mind_events WHERE profile_id = :profile_id"
        params = {"profile_id": profile_id}

        if event_type:
            base_query += " AND event_type = :event_type"
            params["event_type"] = event_type.value

        if project_id:
            base_query += " AND project_id = :project_id"
            params["project_id"] = project_id

        if workspace_id:
            base_query += " AND workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id

        if start_time:
            base_query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            base_query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        base_query += " ORDER BY timestamp DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_event(row) for row in rows]

    def get_events_by_project(
        self,
        project_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MindEvent]:
        """Get all events for a specific project"""
        base_query = "SELECT * FROM mind_events WHERE project_id = :project_id"
        params: Dict[str, Any] = {"project_id": project_id}

        if start_time:
            base_query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            base_query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        base_query += " ORDER BY timestamp DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_event(row) for row in rows]

    def get_events_by_workspace(
        self,
        workspace_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None,
    ) -> List[MindEvent]:
        """Get all events for a specific workspace with optional cursor-based pagination"""
        base_query = "SELECT * FROM mind_events WHERE workspace_id = :workspace_id"
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if start_time:
            base_query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            base_query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        if before_id:
            base_query += """ AND (timestamp < (SELECT timestamp FROM mind_events WHERE id = :before_id)
                OR (timestamp = (SELECT timestamp FROM mind_events WHERE id = :before_id2) AND id < :before_id3))"""
            params["before_id"] = before_id
            params["before_id2"] = before_id
            params["before_id3"] = before_id

        base_query += " ORDER BY timestamp DESC, id DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_event(row) for row in rows]

    def get_events_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None,
    ) -> List[MindEvent]:
        """Get all events for a specific conversation thread"""
        base_query = "SELECT * FROM mind_events WHERE workspace_id = :workspace_id AND thread_id = :thread_id"
        params: Dict[str, Any] = {"workspace_id": workspace_id, "thread_id": thread_id}

        if start_time:
            base_query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            base_query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        if before_id:
            base_query += """ AND (timestamp < (SELECT timestamp FROM mind_events WHERE id = :before_id)
                OR (timestamp = (SELECT timestamp FROM mind_events WHERE id = :before_id2) AND id < :before_id3))"""
            params["before_id"] = before_id
            params["before_id2"] = before_id
            params["before_id3"] = before_id

        base_query += " ORDER BY timestamp DESC, id DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_event(row) for row in rows]

    def count_messages_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        include_execution_chat: bool = False,
    ) -> int:
        """Count MESSAGE events for a specific conversation thread"""
        from app.models.mindscape import EventType

        if include_execution_chat:
            query = text(
                """
                SELECT COUNT(*) as cnt FROM mind_events
                WHERE workspace_id = :workspace_id
                  AND thread_id = :thread_id
                  AND (event_type = :msg_type OR event_type = :exec_type)
            """
            )
            params = {
                "workspace_id": workspace_id,
                "thread_id": thread_id,
                "msg_type": EventType.MESSAGE.value,
                "exec_type": EventType.EXECUTION_CHAT.value,
            }
        else:
            query = text(
                """
                SELECT COUNT(*) as cnt FROM mind_events
                WHERE workspace_id = :workspace_id
                  AND thread_id = :thread_id
                  AND event_type = :msg_type
            """
            )
            params = {
                "workspace_id": workspace_id,
                "thread_id": thread_id,
                "msg_type": EventType.MESSAGE.value,
            }

        with self.get_connection() as conn:
            result = conn.execute(query, params)
            row = result.fetchone()
            return row.cnt if row else 0

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
        """Get timeline events"""
        base_query = "SELECT * FROM mind_events WHERE profile_id = :profile_id"
        params = {"profile_id": profile_id}

        if project_id:
            base_query += " AND project_id = :project_id"
            params["project_id"] = project_id

        if workspace_id:
            base_query += " AND workspace_id = :workspace_id"
            params["workspace_id"] = workspace_id

        if start_time:
            base_query += " AND timestamp >= :start_time"
            params["start_time"] = start_time

        if end_time:
            base_query += " AND timestamp <= :end_time"
            params["end_time"] = end_time

        if event_types:
            # SQLAlchemy handles list binding for IN clauses well with expanding IN params usually
            # But text() binding might need manual expansion or tuple.
            # Safest approach with raw text is manual placeholder expansion.
            # However, simpler to iteratively build or just use single if len=1
            # For simplicity in this raw SQL adapter:
            placeholders = [f":et{i}" for i in range(len(event_types))]
            base_query += f" AND event_type IN ({', '.join(placeholders)})"
            for i, et in enumerate(event_types):
                params[f"et{i}"] = et.value

        base_query += " ORDER BY timestamp DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> MindEvent:
        """Convert database row to MindEvent"""
        return MindEvent(
            id=row.id,
            timestamp=row.timestamp,
            actor=EventActor(row.actor),
            channel=row.channel,
            profile_id=row.profile_id,
            project_id=row.project_id,
            workspace_id=row.workspace_id,
            thread_id=row.thread_id,
            event_type=EventType(row.event_type),
            payload=self.deserialize_json(row.payload, default={}),
            entity_ids=self.deserialize_json(row.entity_ids, default=[]),
            metadata=self.deserialize_json(row.metadata, default={}),
        )
