"""Lens Composition store for data persistence."""
import logging
from datetime import datetime
from typing import List, Optional

from .base import StoreBase
from ...models.lens_composition import LensComposition, LensReference

logger = logging.getLogger(__name__)


class LensCompositionStore(StoreBase):
    """Store for managing Lens Compositions."""

    def create_composition(self, composition: LensComposition) -> LensComposition:
        """
        Create a new composition.

        Args:
            composition: Composition to create

        Returns:
            Created composition
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO lens_compositions (
                    composition_id, workspace_id, name, description,
                    lens_stack, fusion_strategy, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                composition.composition_id,
                composition.workspace_id,
                composition.name,
                composition.description,
                self.serialize_json([l.dict() for l in composition.lens_stack]),
                composition.fusion_strategy,
                self.serialize_json(composition.metadata),
                self.to_isoformat(composition.created_at or datetime.utcnow()),
                self.to_isoformat(composition.updated_at or datetime.utcnow())
            ))
            logger.info(f"Created Lens Composition: {composition.composition_id}")
            return composition

    def get_composition(self, composition_id: str) -> Optional[LensComposition]:
        """
        Get composition by ID.

        Args:
            composition_id: Composition ID

        Returns:
            Composition or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM lens_compositions WHERE composition_id = ?', (composition_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_composition(row)

    def update_composition(
        self,
        composition_id: str,
        updates: dict
    ) -> Optional[LensComposition]:
        """
        Update composition.

        Args:
            composition_id: Composition ID
            updates: Update fields

        Returns:
            Updated composition or None if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            set_clauses = []
            params = []

            if 'name' in updates:
                set_clauses.append('name = ?')
                params.append(updates['name'])

            if 'description' in updates:
                set_clauses.append('description = ?')
                params.append(updates['description'])

            if 'lens_stack' in updates:
                set_clauses.append('lens_stack = ?')
                params.append(self.serialize_json([l.dict() if hasattr(l, 'dict') else l for l in updates['lens_stack']]))

            if 'fusion_strategy' in updates:
                set_clauses.append('fusion_strategy = ?')
                params.append(updates['fusion_strategy'])

            if 'metadata' in updates:
                set_clauses.append('metadata = ?')
                params.append(self.serialize_json(updates['metadata']))

            if not set_clauses:
                return self.get_composition(composition_id)

            set_clauses.append('updated_at = ?')
            params.append(self.to_isoformat(datetime.utcnow()))
            params.append(composition_id)

            cursor.execute(
                f'UPDATE lens_compositions SET {", ".join(set_clauses)} WHERE composition_id = ?',
                params
            )

            if cursor.rowcount == 0:
                return None

            logger.info(f"Updated Lens Composition: {composition_id}")
            return self.get_composition(composition_id)

    def delete_composition(self, composition_id: str) -> bool:
        """
        Delete composition.

        Args:
            composition_id: Composition ID

        Returns:
            True if deleted, False if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM lens_compositions WHERE composition_id = ?', (composition_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted Lens Composition: {composition_id}")
            return deleted

    def list_compositions(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 50
    ) -> List[LensComposition]:
        """
        List compositions with filters.

        Args:
            workspace_id: Optional workspace filter
            limit: Maximum number of results

        Returns:
            List of compositions
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if workspace_id:
                cursor.execute(
                    'SELECT * FROM lens_compositions WHERE workspace_id = ? ORDER BY updated_at DESC LIMIT ?',
                    (workspace_id, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM lens_compositions ORDER BY updated_at DESC LIMIT ?',
                    (limit,)
                )
            rows = cursor.fetchall()
            return [self._row_to_composition(row) for row in rows]

    def _row_to_composition(self, row) -> LensComposition:
        """Convert database row to LensComposition."""
        lens_stack_data = self.deserialize_json(row['lens_stack'], default=[])
        lens_stack = [LensReference(**l) for l in lens_stack_data]

        return LensComposition(
            composition_id=row['composition_id'],
            workspace_id=row['workspace_id'],
            name=row['name'],
            description=row['description'],
            lens_stack=lens_stack,
            fusion_strategy=row['fusion_strategy'] or 'priority_then_weighted',
            metadata=self.deserialize_json(row['metadata']),
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )







