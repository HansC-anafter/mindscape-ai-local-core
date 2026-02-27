"""PostgreSQL implementation of TimelineItemsStore."""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.workspace import TimelineItem, TimelineItemType

logger = logging.getLogger(__name__)


class PostgresTimelineItemsStore(PostgresStoreBase):
    """Postgres implementation of TimelineItemsStore."""

    def create_timeline_item(self, item: TimelineItem) -> TimelineItem:
        """Create a new timeline item record."""
        query = text(
            """
            INSERT INTO timeline_items (
                id, workspace_id, message_id, task_id, type,
                title, summary, data, cta, created_at
            ) VALUES (
                :id, :workspace_id, :message_id, :task_id, :type,
                :title, :summary, :data, :cta, :created_at
            )
        """
        )
        params = {
            "id": item.id,
            "workspace_id": item.workspace_id,
            "message_id": item.message_id,
            "task_id": item.task_id,
            "type": item.type.value,
            "title": item.title,
            "summary": item.summary,
            "data": self.serialize_json(item.data),
            "cta": self.serialize_json(item.cta),
            "created_at": item.created_at,
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        logger.info(
            f"Created timeline item: {item.id} "
            f"(workspace: {item.workspace_id}, type: {item.type.value})"
        )
        return item

    def get_timeline_item(self, item_id: str) -> Optional[TimelineItem]:
        """Get timeline item by ID."""
        query = text("SELECT * FROM timeline_items WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": item_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_timeline_item(row)

    def list_timeline_items_by_workspace(
        self,
        workspace_id: str,
        message_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[TimelineItem]:
        """List timeline items for a workspace."""
        base_query = "SELECT * FROM timeline_items WHERE workspace_id = :workspace_id"
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if message_id:
            base_query += " AND message_id = :message_id"
            params["message_id"] = message_id

        base_query += " ORDER BY created_at DESC"

        if limit:
            base_query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_timeline_item(row) for row in rows]

    def list_timeline_items_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> List[TimelineItem]:
        """List timeline items for a specific thread (via mind_events.message_id join)."""
        base_query = """
            SELECT ti.*
            FROM timeline_items ti
            INNER JOIN mind_events e ON e.id = ti.message_id
            WHERE ti.workspace_id = :workspace_id AND e.thread_id = :thread_id
            ORDER BY ti.created_at DESC
        """
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "thread_id": thread_id,
        }

        if limit:
            base_query += " LIMIT :limit"
            params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_timeline_item(row) for row in rows]

    def list_timeline_items_by_message(self, message_id: str) -> List[TimelineItem]:
        """List timeline items for a specific message."""
        query = text(
            "SELECT * FROM timeline_items WHERE message_id = :message_id "
            "ORDER BY created_at DESC"
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"message_id": message_id})
            rows = result.fetchall()
            return [self._row_to_timeline_item(row) for row in rows]

    def update_timeline_item(
        self,
        item_id: str,
        data: Optional[Dict[str, Any]] = None,
        cta: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Update timeline item data and/or CTA."""
        try:
            updates = []
            params: Dict[str, Any] = {"id": item_id}

            if data is not None:
                updates.append("data = :data")
                params["data"] = self.serialize_json(data)

            if cta is not None:
                updates.append("cta = :cta")
                params["cta"] = self.serialize_json(cta) if cta else None

            if updates:
                query = text(
                    f"UPDATE timeline_items SET {', '.join(updates)} WHERE id = :id"
                )
                with self.transaction() as conn:
                    result = conn.execute(query, params)
                    return result.rowcount > 0
            return False
        except Exception as e:
            logger.error(f"Failed to update timeline item {item_id}: {e}")
            return False

    def _row_to_timeline_item(self, row) -> TimelineItem:
        """Convert database row to TimelineItem model."""
        # Handle cta field
        cta_raw = self.deserialize_json(row.cta) if row.cta else None
        if isinstance(cta_raw, list):
            cta = cta_raw
        else:
            cta = None

        return TimelineItem(
            id=row.id,
            workspace_id=row.workspace_id,
            message_id=row.message_id,
            task_id=row.task_id if row.task_id else None,
            type=TimelineItemType(row.type),
            title=row.title,
            summary=row.summary,
            data=self.deserialize_json(row.data, default={}),
            cta=cta,
            created_at=row.created_at,
        )
