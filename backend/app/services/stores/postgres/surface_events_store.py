from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

from .remaining_store_utils import _utc_now

logger = logging.getLogger(__name__)


# =================================================================================
# Surface Events Store
# =================================================================================
class PostgresSurfaceEventsStore(PostgresStoreBase):
    """Postgres implementation of SurfaceEventsStore."""

    def create_event(self, event: SurfaceEvent) -> SurfaceEvent:
        with self.transaction() as conn:
            query = text(
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
            )
            params = {
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
            }
            conn.execute(query, params)
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
        with self.get_connection() as conn:
            query_str = "SELECT * FROM surface_events WHERE workspace_id = :workspace_id"
            params = {"workspace_id": workspace_id, "limit": limit}

            if surface_filter:
                query_str += " AND source_surface = :source_surface"
                params["source_surface"] = surface_filter

            if event_type_filter:
                query_str += " AND event_type = :event_type"
                params["event_type"] = event_type_filter

            if actor_filter:
                query_str += " AND actor_id = :actor_id"
                params["actor_id"] = actor_filter

            if command_id_filter:
                query_str += " AND command_id = :command_id"
                params["command_id"] = command_id_filter

            if thread_id_filter:
                query_str += " AND thread_id = :thread_id"
                params["thread_id"] = thread_id_filter

            if correlation_id_filter:
                query_str += " AND correlation_id = :correlation_id"
                params["correlation_id"] = correlation_id_filter

            if pack_id_filter:
                query_str += " AND pack_id = :pack_id"
                params["pack_id"] = pack_id_filter

            if card_id_filter:
                query_str += " AND card_id = :card_id"
                params["card_id"] = card_id_filter

            query_str += " ORDER BY created_at DESC LIMIT :limit"
            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> SurfaceEvent:
        return SurfaceEvent(
            event_id=row.event_id,
            workspace_id=row.workspace_id,
            source_surface=row.source_surface,
            event_type=row.event_type,
            actor_id=row.actor_id,
            payload=self.deserialize_json(row.payload, default={}),
            command_id=row.command_id,
            thread_id=row.thread_id,
            correlation_id=row.correlation_id,
            parent_event_id=row.parent_event_id,
            execution_id=row.execution_id,
            pack_id=row.pack_id,
            card_id=row.card_id,
            scope=row.scope,
            playbook_version=row.playbook_version,
            timestamp=row.timestamp,
            created_at=row.created_at,
        )
