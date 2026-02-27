"""PostgreSQL implementation of EntitiesStore."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import text
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.mindscape import Entity, Tag, EntityTag, EntityType, TagCategory
import logging

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PostgresEntitiesStore(PostgresStoreBase):
    """Postgres implementation of EntitiesStore (entities + tags + entity_tags)."""

    # ==================== Entity Methods ====================

    def create_entity(self, entity: Entity) -> Entity:
        """Create a new entity."""
        query = text(
            """
            INSERT INTO entities (
                id, entity_type, name, profile_id, description,
                created_at, updated_at
            ) VALUES (
                :id, :entity_type, :name, :profile_id, :description,
                :created_at, :updated_at
            )
        """
        )
        params = {
            "id": entity.id,
            "entity_type": entity.entity_type.value,
            "name": entity.name,
            "profile_id": entity.profile_id,
            "description": entity.description,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID."""
        query = text("SELECT * FROM entities WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": entity_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def list_entities(
        self,
        profile_id: Optional[str] = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
    ) -> List[Entity]:
        """List entities with optional filters."""
        base_query = "SELECT * FROM entities WHERE 1=1"
        params: Dict[str, Any] = {}

        if profile_id:
            base_query += " AND profile_id = :profile_id"
            params["profile_id"] = profile_id

        if entity_type:
            base_query += " AND entity_type = :entity_type"
            params["entity_type"] = entity_type.value

        base_query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_entity(row) for row in rows]

    def update_entity(
        self, entity_id: str, updates: Dict[str, Any]
    ) -> Optional[Entity]:
        """Update entity fields."""
        set_clauses = []
        params: Dict[str, Any] = {"id": entity_id}

        if "name" in updates:
            set_clauses.append("name = :name")
            params["name"] = updates["name"]

        if "description" in updates:
            set_clauses.append("description = :description")
            params["description"] = updates["description"]

        if set_clauses:
            set_clauses.append("updated_at = :updated_at")
            params["updated_at"] = _utc_now()

            query = text(f"UPDATE entities SET {', '.join(set_clauses)} WHERE id = :id")
            with self.transaction() as conn:
                result = conn.execute(query, params)
                if result.rowcount > 0:
                    return self.get_entity(entity_id)
        return None

    def _row_to_entity(self, row) -> Entity:
        """Convert database row to Entity."""
        return Entity(
            id=row.id,
            entity_type=EntityType(row.entity_type),
            name=row.name,
            profile_id=row.profile_id,
            description=row.description,
            metadata={},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    # ==================== Tag Methods ====================

    def create_tag(self, tag: Tag) -> Tag:
        """Create a new tag."""
        query = text(
            """
            INSERT INTO tags (
                id, name, category, profile_id, description, color, metadata, created_at
            ) VALUES (
                :id, :name, :category, :profile_id, :description, :color, :metadata, :created_at
            )
        """
        )
        params = {
            "id": tag.id,
            "name": tag.name,
            "category": tag.category.value,
            "profile_id": tag.profile_id,
            "description": tag.description,
            "color": tag.color,
            "metadata": self.serialize_json(tag.metadata),
            "created_at": tag.created_at,
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return tag

    def get_tag(self, tag_id: str) -> Optional[Tag]:
        """Get tag by ID."""
        query = text("SELECT * FROM tags WHERE id = :id")
        with self.get_connection() as conn:
            result = conn.execute(query, {"id": tag_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_tag(row)

    def list_tags(
        self,
        profile_id: Optional[str] = None,
        category: Optional[TagCategory] = None,
        limit: int = 100,
    ) -> List[Tag]:
        """List tags with optional filters."""
        base_query = "SELECT * FROM tags WHERE 1=1"
        params: Dict[str, Any] = {}

        if profile_id:
            base_query += " AND profile_id = :profile_id"
            params["profile_id"] = profile_id

        if category:
            base_query += " AND category = :category"
            params["category"] = category.value

        base_query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_tag(row) for row in rows]

    def _row_to_tag(self, row) -> Tag:
        """Convert database row to Tag."""
        return Tag(
            id=row.id,
            name=row.name,
            category=TagCategory(row.category),
            profile_id=row.profile_id,
            description=row.description,
            color=row.color,
            metadata=self.deserialize_json(row.metadata, default={}),
            created_at=row.created_at,
        )

    # ==================== Entity-Tag Association Methods ====================

    def tag_entity(
        self, entity_id: str, tag_id: str, value: Optional[str] = None
    ) -> EntityTag:
        """Tag an entity with a tag."""
        entity_tag = EntityTag(
            entity_id=entity_id,
            tag_id=tag_id,
            value=value,
            created_at=_utc_now(),
        )
        query = text(
            """
            INSERT INTO entity_tags (entity_id, tag_id, value, created_at)
            VALUES (:entity_id, :tag_id, :value, :created_at)
            ON CONFLICT (entity_id, tag_id) DO UPDATE
            SET value = EXCLUDED.value, created_at = EXCLUDED.created_at
        """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "entity_id": entity_id,
                    "tag_id": tag_id,
                    "value": value,
                    "created_at": entity_tag.created_at,
                },
            )
        return entity_tag

    def untag_entity(self, entity_id: str, tag_id: str) -> bool:
        """Remove a tag from an entity."""
        query = text(
            "DELETE FROM entity_tags WHERE entity_id = :entity_id AND tag_id = :tag_id"
        )
        with self.transaction() as conn:
            result = conn.execute(
                query,
                {
                    "entity_id": entity_id,
                    "tag_id": tag_id,
                },
            )
            return result.rowcount > 0

    def get_tags_by_entity(self, entity_id: str) -> List[Tag]:
        """Get all tags associated with an entity."""
        query = text(
            """
            SELECT t.*
            FROM tags t
            INNER JOIN entity_tags et ON t.id = et.tag_id
            WHERE et.entity_id = :entity_id
            ORDER BY et.created_at DESC
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"entity_id": entity_id})
            rows = result.fetchall()
            return [self._row_to_tag(row) for row in rows]

    def get_entities_by_tag(self, tag_id: str, limit: int = 100) -> List[Entity]:
        """Get all entities tagged with a specific tag."""
        query = text(
            """
            SELECT e.*
            FROM entities e
            INNER JOIN entity_tags et ON e.id = et.entity_id
            WHERE et.tag_id = :tag_id
            ORDER BY et.created_at DESC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(query, {"tag_id": tag_id, "limit": limit})
            rows = result.fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_entities_by_tags(
        self,
        tag_ids: List[str],
        profile_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Entity]:
        """Get entities that have all specified tags (AND logic)."""
        if not tag_ids:
            return []

        # Build parameterized IN clause
        tag_params = {f"tag{i}": tid for i, tid in enumerate(tag_ids)}
        placeholders = ", ".join(f":tag{i}" for i in range(len(tag_ids)))

        base_query = f"""
            SELECT e.*
            FROM entities e
            WHERE e.id IN (
                SELECT et.entity_id
                FROM entity_tags et
                WHERE et.tag_id IN ({placeholders})
                GROUP BY et.entity_id
                HAVING COUNT(DISTINCT et.tag_id) = :tag_count
            )
        """
        params: Dict[str, Any] = {**tag_params, "tag_count": len(tag_ids)}

        if profile_id:
            base_query += " AND e.profile_id = :profile_id"
            params["profile_id"] = profile_id

        base_query += " ORDER BY e.created_at DESC LIMIT :limit"
        params["limit"] = limit

        with self.get_connection() as conn:
            result = conn.execute(text(base_query), params)
            rows = result.fetchall()
            return [self._row_to_entity(row) for row in rows]
