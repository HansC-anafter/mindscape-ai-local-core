"""
Entities and Tags store for Mindscape data persistence
Handles entity, tag, and entity-tag association CRUD operations
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase
from ...models.mindscape import Entity, Tag, EntityTag, EntityType, TagCategory
import logging

logger = logging.getLogger(__name__)


class EntitiesStore(StoreBase):
    """Store for managing entities, tags, and their associations"""

    # ==================== Entity Methods ====================

    def create_entity(self, entity: Entity) -> Entity:
        """Create a new entity"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO entities (
                    id, entity_type, name, profile_id, description, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entity.id,
                entity.entity_type.value,
                entity.name,
                entity.profile_id,
                entity.description,
                self.serialize_json(entity.metadata),
                self.to_isoformat(entity.created_at),
                self.to_isoformat(entity.updated_at)
            ))
            conn.commit()
            return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM entities WHERE id = ?', (entity_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def list_entities(
        self,
        profile_id: Optional[str] = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 100
    ) -> List[Entity]:
        """List entities with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM entities WHERE 1=1'
            params = []

            if profile_id:
                query += ' AND profile_id = ?'
                params.append(profile_id)

            if entity_type:
                query += ' AND entity_type = ?'
                params.append(entity_type.value)

            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]

    def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> Optional[Entity]:
        """Update entity fields"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            set_clauses = []
            params = []

            if 'name' in updates:
                set_clauses.append('name = ?')
                params.append(updates['name'])

            if 'description' in updates:
                set_clauses.append('description = ?')
                params.append(updates['description'])

            if 'metadata' in updates:
                set_clauses.append('metadata = ?')
                params.append(self.serialize_json(updates['metadata']))

            if set_clauses:
                set_clauses.append('updated_at = ?')
                params.append(self.to_isoformat(datetime.utcnow()))
                params.append(entity_id)

                cursor.execute(
                    f'UPDATE entities SET {", ".join(set_clauses)} WHERE id = ?',
                    params
                )
                conn.commit()

                if cursor.rowcount > 0:
                    return self.get_entity(entity_id)
            return None

    def _row_to_entity(self, row) -> Entity:
        """Convert database row to Entity"""
        return Entity(
            id=row['id'],
            entity_type=EntityType(row['entity_type']),
            name=row['name'],
            profile_id=row['profile_id'],
            description=row['description'],
            metadata=self.deserialize_json(row['metadata'], {}),
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

    # ==================== Tag Methods ====================

    def create_tag(self, tag: Tag) -> Tag:
        """Create a new tag"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tags (
                    id, name, category, profile_id, description, color, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                tag.id,
                tag.name,
                tag.category.value,
                tag.profile_id,
                tag.description,
                tag.color,
                self.serialize_json(tag.metadata),
                self.to_isoformat(tag.created_at)
            ))
            conn.commit()
            return tag

    def get_tag(self, tag_id: str) -> Optional[Tag]:
        """Get tag by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tags WHERE id = ?', (tag_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_tag(row)

    def list_tags(
        self,
        profile_id: Optional[str] = None,
        category: Optional[TagCategory] = None,
        limit: int = 100
    ) -> List[Tag]:
        """List tags with optional filters"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM tags WHERE 1=1'
            params = []

            if profile_id:
                query += ' AND profile_id = ?'
                params.append(profile_id)

            if category:
                query += ' AND category = ?'
                params.append(category.value)

            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_tag(row) for row in rows]

    def _row_to_tag(self, row) -> Tag:
        """Convert database row to Tag"""
        return Tag(
            id=row['id'],
            name=row['name'],
            category=TagCategory(row['category']),
            profile_id=row['profile_id'],
            description=row['description'],
            color=row['color'],
            metadata=self.deserialize_json(row['metadata'], {}),
            created_at=self.from_isoformat(row['created_at'])
        )

    # ==================== Entity-Tag Association Methods ====================

    def tag_entity(self, entity_id: str, tag_id: str, value: Optional[str] = None) -> EntityTag:
        """Tag an entity with a tag"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            entity_tag = EntityTag(
                entity_id=entity_id,
                tag_id=tag_id,
                value=value,
                created_at=datetime.utcnow()
            )
            cursor.execute('''
                INSERT OR REPLACE INTO entity_tags (entity_id, tag_id, value, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                entity_id,
                tag_id,
                value,
                self.to_isoformat(entity_tag.created_at)
            ))
            conn.commit()
            return entity_tag

    def untag_entity(self, entity_id: str, tag_id: str) -> bool:
        """Remove a tag from an entity"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM entity_tags WHERE entity_id = ? AND tag_id = ?
            ''', (entity_id, tag_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_tags_by_entity(self, entity_id: str) -> List[Tag]:
        """Get all tags associated with an entity"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT t.*, et.value as tag_value
                FROM tags t
                INNER JOIN entity_tags et ON t.id = et.tag_id
                WHERE et.entity_id = ?
                ORDER BY et.created_at DESC
            ''', (entity_id,))
            rows = cursor.fetchall()
            return [self._row_to_tag(row) for row in rows]

    def get_entities_by_tag(self, tag_id: str, limit: int = 100) -> List[Entity]:
        """Get all entities tagged with a specific tag"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT e.*
                FROM entities e
                INNER JOIN entity_tags et ON e.id = et.entity_id
                WHERE et.tag_id = ?
                ORDER BY et.created_at DESC
                LIMIT ?
            ''', (tag_id, limit))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]

    def get_entities_by_tags(
        self,
        tag_ids: List[str],
        profile_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Entity]:
        """Get entities that have all specified tags (AND logic)"""
        if not tag_ids:
            return []

        with self.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(tag_ids))
            query = f'''
                SELECT e.*
                FROM entities e
                WHERE e.id IN (
                    SELECT et.entity_id
                    FROM entity_tags et
                    WHERE et.tag_id IN ({placeholders})
                    GROUP BY et.entity_id
                    HAVING COUNT(DISTINCT et.tag_id) = ?
                )
            '''
            params = list(tag_ids) + [len(tag_ids)]

            if profile_id:
                query += ' AND e.profile_id = ?'
                params.append(profile_id)

            query += ' ORDER BY e.created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
