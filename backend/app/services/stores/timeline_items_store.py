"""
TimelineItems store for managing timeline result cards

TimelineItems are derived from MindEvents and represent Pack execution results.
All timeline item writes go through the /chat flow, ensuring single source of truth.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase, StoreNotFoundError
from ...models.workspace import TimelineItem, TimelineItemType

logger = logging.getLogger(__name__)


class TimelineItemsStore(StoreBase):
    """Store for managing timeline item records"""

    def create_timeline_item(self, item: TimelineItem) -> TimelineItem:
        """
        Create a new timeline item record

        Args:
            item: TimelineItem model instance

        Returns:
            Created timeline item
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO timeline_items (
                    id, workspace_id, message_id, task_id, type,
                    title, summary, data, cta, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item.id,
                item.workspace_id,
                item.message_id,
                item.task_id,
                item.type.value,
                item.title,
                item.summary,
                self.serialize_json(item.data),
                self.serialize_json(item.cta),
                self.to_isoformat(item.created_at)
            ))
            logger.info(f"Created timeline item: {item.id} (workspace: {item.workspace_id}, type: {item.type.value})")
            return item

    def get_timeline_item(self, item_id: str) -> Optional[TimelineItem]:
        """
        Get timeline item by ID

        Args:
            item_id: Timeline item ID

        Returns:
            TimelineItem model or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM timeline_items WHERE id = ?', (item_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_timeline_item(row)

    def list_timeline_items_by_workspace(
        self,
        workspace_id: str,
        message_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[TimelineItem]:
        """
        List timeline items for a workspace

        Args:
            workspace_id: Workspace ID
            message_id: Filter by message ID (optional)
            limit: Maximum number of items to return (optional)

        Returns:
            List of timeline items, ordered by created_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM timeline_items WHERE workspace_id = ?'
            params = [workspace_id]

            if message_id:
                query += ' AND message_id = ?'
                params.append(message_id)

            query += ' ORDER BY created_at DESC'

            if limit:
                query += ' LIMIT ?'
                params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_timeline_item(row) for row in rows]

    def list_timeline_items_by_message(self, message_id: str) -> List[TimelineItem]:
        """
        List timeline items for a specific message

        Args:
            message_id: Message ID

        Returns:
            List of timeline items for the message
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM timeline_items WHERE message_id = ? ORDER BY created_at DESC',
                (message_id,)
            )
            rows = cursor.fetchall()
            return [self._row_to_timeline_item(row) for row in rows]

    def update_timeline_item(
        self,
        item_id: str,
        data: Optional[Dict[str, Any]] = None,
        cta: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Update timeline item data and/or CTA

        Args:
            item_id: Timeline item ID
            data: Updated data dict (optional)
            cta: Updated CTA list (optional, set to None to remove CTA)

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                updates = []
                params = []

                if data is not None:
                    updates.append('data = ?')
                    params.append(self.serialize_json(data))

                if cta is not None:
                    updates.append('cta = ?')
                    params.append(self.serialize_json(cta) if cta else None)

                if updates:
                    params.append(item_id)
                    query = f'UPDATE timeline_items SET {", ".join(updates)} WHERE id = ?'
                    cursor.execute(query, params)
                    return cursor.rowcount > 0
                return False
        except Exception as e:
            logger.error(f"Failed to update timeline item {item_id}: {e}")
            return False

    def _row_to_timeline_item(self, row) -> TimelineItem:
        """Convert database row to TimelineItem model"""
        # Handle cta field: it should be a list, but database might have dict or None
        cta_raw = self.deserialize_json(row['cta'])
        if cta_raw is None:
            cta = None
        elif isinstance(cta_raw, list):
            cta = cta_raw
        elif isinstance(cta_raw, dict):
            # If it's a dict (e.g., {}), convert to None (TimelineItem expects Optional[List])
            cta = None
        else:
            cta = None

        return TimelineItem(
            id=row['id'],
            workspace_id=row['workspace_id'],
            message_id=row['message_id'],
            task_id=row['task_id'] if row['task_id'] else None,  # Handle None task_id
            type=TimelineItemType(row['type']),
            title=row['title'],
            summary=row['summary'],
            data=self.deserialize_json(row['data'], {}),
            cta=cta,
            created_at=self.from_isoformat(row['created_at'])
        )
