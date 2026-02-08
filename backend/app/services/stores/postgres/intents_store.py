from typing import List, Optional
from sqlalchemy import text
from app.services.stores.postgres_base import PostgresStoreBase
from app.models.mindscape import IntentCard, IntentStatus, PriorityLevel
import logging

logger = logging.getLogger(__name__)


class PostgresIntentsStore(PostgresStoreBase):
    """Postgres implementation of IntentsStore."""

    def create_intent(self, intent: IntentCard) -> IntentCard:
        """Create a new intent"""
        query = text(
            """
            INSERT INTO intents (
                id, profile_id, title, description, status, priority, tags, storyline_tags,
                category, progress_percentage, created_at, updated_at,
                started_at, completed_at, due_date, parent_intent_id,
                child_intent_ids, metadata
            ) VALUES (
                :id, :profile_id, :title, :description, :status, :priority, :tags, :storyline_tags,
                :category, :progress_percentage, :created_at, :updated_at,
                :started_at, :completed_at, :due_date, :parent_intent_id,
                :child_intent_ids, :metadata
            )
        """
        )
        params = {
            "id": intent.id,
            "profile_id": intent.profile_id,
            "title": intent.title,
            "description": intent.description,
            "status": intent.status.value,
            "priority": intent.priority.value,
            "tags": self.serialize_json(intent.tags),
            "storyline_tags": self.serialize_json(intent.storyline_tags),
            "category": intent.category,
            "progress_percentage": intent.progress_percentage,
            "created_at": intent.created_at,
            "updated_at": intent.updated_at,
            "started_at": intent.started_at,
            "completed_at": intent.completed_at,
            "due_date": intent.due_date,
            "parent_intent_id": intent.parent_intent_id,
            "child_intent_ids": self.serialize_json(intent.child_intent_ids),
            "metadata": self.serialize_json(intent.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return intent

    def get_intent(self, intent_id: str) -> Optional[IntentCard]:
        """Get intent by ID"""
        query = text("SELECT * FROM intents WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": intent_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_intent(row)

    def list_intents(
        self,
        profile_id: str,
        status: Optional[IntentStatus] = None,
        priority: Optional[PriorityLevel] = None,
    ) -> List[IntentCard]:
        """List intents for a profile with optional filters"""
        base_query = "SELECT * FROM intents WHERE profile_id = :profile_id"
        params = {"profile_id": profile_id}

        if status:
            base_query += " AND status = :status"
            params["status"] = status.value

        if priority:
            base_query += " AND priority = :priority"
            params["priority"] = priority.value

        base_query += " ORDER BY created_at DESC"

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_intent(row) for row in rows]

    def update_intent(self, intent: IntentCard) -> Optional[IntentCard]:
        """Update an existing intent"""
        query = text(
            """
            UPDATE intents SET
                title = :title,
                description = :description,
                status = :status,
                priority = :priority,
                tags = :tags,
                storyline_tags = :storyline_tags,
                category = :category,
                progress_percentage = :progress_percentage,
                updated_at = :updated_at,
                started_at = :started_at,
                completed_at = :completed_at,
                due_date = :due_date,
                parent_intent_id = :parent_intent_id,
                child_intent_ids = :child_intent_ids,
                metadata = :metadata
            WHERE id = :id
        """
        )
        params = {
            "title": intent.title,
            "description": intent.description,
            "status": intent.status.value,
            "priority": intent.priority.value,
            "tags": self.serialize_json(intent.tags),
            "storyline_tags": self.serialize_json(intent.storyline_tags),
            "category": intent.category,
            "progress_percentage": intent.progress_percentage,
            "updated_at": intent.updated_at,
            "started_at": intent.started_at,
            "completed_at": intent.completed_at,
            "due_date": intent.due_date,
            "parent_intent_id": intent.parent_intent_id,
            "child_intent_ids": self.serialize_json(intent.child_intent_ids),
            "metadata": self.serialize_json(intent.metadata),
            "id": intent.id,
        }
        with self.transaction() as conn:
            result = conn.execute(query, params)
            if result.rowcount > 0:
                return intent
            return None

    def delete_intent(self, intent_id: str) -> bool:
        """Delete an intent by ID"""
        query = text("DELETE FROM intents WHERE id = :id")
        with self.transaction() as conn:
            result = conn.execute(query, {"id": intent_id})
            return result.rowcount > 0

    def _row_to_intent(self, row) -> IntentCard:
        """Convert database row to IntentCard"""
        # Handle storyline_tags field - support backward compatibility if needed
        storyline_tags = (
            self.deserialize_json(row.storyline_tags, default=[])
            if hasattr(row, "storyline_tags") and row.storyline_tags
            else []
        )

        return IntentCard(
            id=row.id,
            profile_id=row.profile_id,
            title=row.title,
            description=row.description,
            status=IntentStatus(row.status),
            priority=PriorityLevel(row.priority),
            tags=self.deserialize_json(row.tags, default=[]),
            storyline_tags=storyline_tags,
            category=row.category,
            progress_percentage=row.progress_percentage,
            created_at=row.created_at,
            updated_at=row.updated_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            due_date=row.due_date,
            parent_intent_id=row.parent_intent_id,
            child_intent_ids=self.deserialize_json(row.child_intent_ids, default=[]),
            metadata=self.deserialize_json(row.metadata, default={}),
        )
