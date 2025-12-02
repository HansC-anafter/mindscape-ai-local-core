"""
Intents store for Mindscape data persistence
Handles intent card CRUD operations
"""

from typing import List, Optional
from backend.app.services.stores.base import StoreBase
from ...models.mindscape import IntentCard, IntentStatus, PriorityLevel
import logging

logger = logging.getLogger(__name__)


class IntentsStore(StoreBase):
    """Store for managing intents"""

    def create_intent(self, intent: IntentCard) -> IntentCard:
        """Create a new intent"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO intents (
                    id, profile_id, title, description, status, priority, tags,
                    category, progress_percentage, created_at, updated_at,
                    started_at, completed_at, due_date, parent_intent_id,
                    child_intent_ids, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                intent.id,
                intent.profile_id,
                intent.title,
                intent.description,
                intent.status.value,
                intent.priority.value,
                self.serialize_json(intent.tags),
                intent.category,
                intent.progress_percentage,
                self.to_isoformat(intent.created_at),
                self.to_isoformat(intent.updated_at),
                self.to_isoformat(intent.started_at),
                self.to_isoformat(intent.completed_at),
                self.to_isoformat(intent.due_date),
                intent.parent_intent_id,
                self.serialize_json(intent.child_intent_ids),
                self.serialize_json(intent.metadata)
            ))
            conn.commit()
            return intent

    def get_intent(self, intent_id: str) -> Optional[IntentCard]:
        """Get intent by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM intents WHERE id = ?', (intent_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_intent(row)

    def list_intents(self, profile_id: str, status: Optional[IntentStatus] = None,
                    priority: Optional[PriorityLevel] = None) -> List[IntentCard]:
        """List intents for a profile with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM intents WHERE profile_id = ?'
            params = [profile_id]

            if status:
                query += ' AND status = ?'
                params.append(status.value)

            if priority:
                query += ' AND priority = ?'
                params.append(priority.value)

            query += ' ORDER BY created_at DESC'
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_intent(row) for row in rows]

    def _row_to_intent(self, row) -> IntentCard:
        """Convert database row to IntentCard"""
        return IntentCard(
            id=row['id'],
            profile_id=row['profile_id'],
            title=row['title'],
            description=row['description'],
            status=IntentStatus(row['status']),
            priority=PriorityLevel(row['priority']),
            tags=self.deserialize_json(row['tags'], []),
            category=row['category'],
            progress_percentage=row['progress_percentage'],
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at']),
            started_at=self.from_isoformat(row['started_at']),
            completed_at=self.from_isoformat(row['completed_at']),
            due_date=self.from_isoformat(row['due_date']),
            parent_intent_id=row['parent_intent_id'],
            child_intent_ids=self.deserialize_json(row['child_intent_ids'], []),
            metadata=self.deserialize_json(row['metadata'], {})
        )
