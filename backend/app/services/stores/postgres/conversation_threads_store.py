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
# Conversation Threads Store
# =================================================================================
class PostgresConversationThreadsStore(PostgresStoreBase):
    """Postgres implementation of ConversationThreadsStore."""

    def create_thread(self, thread: ConversationThread) -> ConversationThread:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO conversation_threads (
                    id, workspace_id, title, project_id, pinned_scope,
                    created_at, updated_at, last_message_at, message_count,
                    metadata, is_default
                ) VALUES (
                    :id, :workspace_id, :title, :project_id, :pinned_scope,
                    :created_at, :updated_at, :last_message_at, :message_count,
                    :metadata, :is_default
                )
            """
            )
            params = {
                "id": thread.id,
                "workspace_id": thread.workspace_id,
                "title": thread.title,
                "project_id": thread.project_id,
                "pinned_scope": thread.pinned_scope,
                "created_at": thread.created_at,
                "updated_at": thread.updated_at,
                "last_message_at": thread.last_message_at,
                "message_count": thread.message_count,
                "metadata": self.serialize_json(thread.metadata),
                "is_default": thread.is_default,
            }
            conn.execute(query, params)
            logger.info(f"Created conversation thread: {thread.id}")
            return thread

    def get_thread(self, thread_id: str) -> Optional[ConversationThread]:
        with self.get_connection() as conn:
            query = text("SELECT * FROM conversation_threads WHERE id = :id")
            row = conn.execute(query, {"id": thread_id}).fetchone()
            if not row:
                return None
            return self._row_to_thread(row)

    def list_threads_by_workspace(
        self, workspace_id: str, limit: Optional[int] = None
    ) -> List[ConversationThread]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM conversation_threads WHERE workspace_id = :workspace_id ORDER BY updated_at DESC"
            params = {"workspace_id": workspace_id}
            if limit:
                query_str += " LIMIT :limit"
                params["limit"] = limit

            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_thread(row) for row in rows]

    def get_default_thread(self, workspace_id: str) -> Optional[ConversationThread]:
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM conversation_threads WHERE workspace_id = :workspace_id AND is_default = :is_default LIMIT 1"
            )
            row = conn.execute(
                query, {"workspace_id": workspace_id, "is_default": True}
            ).fetchone()
            if not row:
                return None
            return self._row_to_thread(row)

    def update_thread(self, thread_id: str, **kwargs) -> Optional[ConversationThread]:
        # Simplify update logic by fetching first if needed, similar to generic store pattern
        # Or implement partial update directly
        current = self.get_thread(thread_id)
        if not current:
            return None

        updates = []
        params = {"id": thread_id}

        # Handling specific fields from kwargs matching original signature
        mappings = {
            "title": "title",
            "project_id": "project_id",
            "pinned_scope": "pinned_scope",
            "last_message_at": "last_message_at",
            "message_count": "message_count",
        }

        for arg_name, col_name in mappings.items():
            if arg_name in kwargs and kwargs[arg_name] is not None:
                updates.append(f"{col_name} = :{col_name}")
                params[col_name] = kwargs[arg_name]

        if "metadata" in kwargs and kwargs["metadata"] is not None:
            merged_metadata = {**current.metadata, **kwargs["metadata"]}
            updates.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(merged_metadata)

        if not updates:
            return current

        updates.append("updated_at = :updated_at")
        params["updated_at"] = datetime.now(timezone.utc)

        with self.transaction() as conn:
            query = text(
                f"UPDATE conversation_threads SET {', '.join(updates)} WHERE id = :id"
            )
            conn.execute(query, params)
            return self.get_thread(thread_id)

    def delete_thread(self, thread_id: str) -> bool:
        with self.transaction() as conn:
            query = text("DELETE FROM conversation_threads WHERE id = :id")
            result = conn.execute(query, {"id": thread_id})
            return result.rowcount > 0

    def _row_to_thread(self, row) -> ConversationThread:
        return ConversationThread(
            id=row.id,
            workspace_id=row.workspace_id,
            title=row.title,
            project_id=row.project_id,
            pinned_scope=row.pinned_scope,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_message_at=row.last_message_at,
            message_count=row.message_count or 0,
            metadata=self.deserialize_json(row.metadata, {}),
            is_default=row.is_default if row.is_default is not None else False,
        )
