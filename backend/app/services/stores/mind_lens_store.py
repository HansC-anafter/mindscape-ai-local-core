"""Mind Lens store for data persistence."""
import logging
from datetime import datetime
from typing import List, Optional

from .base import StoreBase, StoreNotFoundError
from ...models.mind_lens import MindLensSchema, MindLensInstance, LensSpec

logger = logging.getLogger(__name__)


class MindLensStore(StoreBase):
    """Store for managing Mind Lens schemas and instances."""

    def create_schema(self, schema: MindLensSchema) -> MindLensSchema:
        """
        Create a new Mind Lens schema.

        Args:
            schema: Schema to create

        Returns:
            Created schema
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mind_lens_schemas (
                    schema_id, role, label, dimensions, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                schema.schema_id,
                schema.role,
                schema.label,
                self.serialize_json([d.dict() for d in schema.dimensions]),
                schema.version,
                self.to_isoformat(schema.created_at or datetime.utcnow()),
                self.to_isoformat(schema.updated_at or datetime.utcnow())
            ))
            logger.info(f"Created Mind Lens schema: {schema.schema_id}")
            return schema

    def get_schema(self, schema_id: str) -> Optional[MindLensSchema]:
        """
        Get schema by ID.

        Args:
            schema_id: Schema ID

        Returns:
            Schema or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_lens_schemas WHERE schema_id = ?', (schema_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_schema(row)

    def get_schema_by_role(self, role: str) -> Optional[MindLensSchema]:
        """
        Get schema by role.

        Args:
            role: Role name

        Returns:
            Schema or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_lens_schemas WHERE role = ? ORDER BY version DESC LIMIT 1', (role,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_schema(row)

    def create_instance(self, instance: MindLensInstance) -> MindLensInstance:
        """
        Create a new Mind Lens instance.

        Args:
            instance: Instance to create

        Returns:
            Created instance
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mind_lens_instances (
                    mind_lens_id, schema_id, owner_user_id, role, label, description,
                    "values", source, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                instance.mind_lens_id,
                instance.schema_id,
                instance.owner_user_id,
                instance.role,
                instance.label,
                instance.description,
                self.serialize_json(instance.values),
                self.serialize_json(instance.source),
                instance.version,
                self.to_isoformat(instance.created_at or datetime.utcnow()),
                self.to_isoformat(instance.updated_at or datetime.utcnow())
            ))
            logger.info(f"Created Mind Lens instance: {instance.mind_lens_id}")
            return instance

    def get_instance(self, instance_id: str) -> Optional[MindLensInstance]:
        """
        Get instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_lens_instances WHERE mind_lens_id = ?', (instance_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_instance(row)

    def list_instances(
        self,
        owner_user_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50
    ) -> List[MindLensInstance]:
        """
        List instances with filters.

        Args:
            owner_user_id: Optional owner filter
            role: Optional role filter
            limit: Maximum number of results

        Returns:
            List of instances
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM mind_lens_instances WHERE 1=1'
            params = []

            if owner_user_id:
                query += ' AND owner_user_id = ?'
                params.append(owner_user_id)

            if role:
                query += ' AND role = ?'
                params.append(role)

            query += ' ORDER BY updated_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_instance(row) for row in rows]

    def update_instance(
        self,
        instance_id: str,
        updates: dict
    ) -> Optional[MindLensInstance]:
        """
        Update instance.

        Args:
            instance_id: Instance ID
            updates: Update fields

        Returns:
            Updated instance or None if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            set_clauses = []
            params = []

            if 'label' in updates:
                set_clauses.append('label = ?')
                params.append(updates['label'])

            if 'description' in updates:
                set_clauses.append('description = ?')
                params.append(updates['description'])

            if 'values' in updates:
                set_clauses.append('"values" = ?')
                params.append(self.serialize_json(updates['values']))

            if 'source' in updates:
                set_clauses.append('source = ?')
                params.append(self.serialize_json(updates['source']))

            if not set_clauses:
                return self.get_instance(instance_id)

            set_clauses.append('updated_at = ?')
            params.append(self.to_isoformat(datetime.utcnow()))
            params.append(instance_id)

            cursor.execute(
                f'UPDATE mind_lens_instances SET {", ".join(set_clauses)} WHERE mind_lens_id = ?',
                params
            )

            if cursor.rowcount == 0:
                return None

            logger.info(f"Updated Mind Lens instance: {instance_id}")
            return self.get_instance(instance_id)

    def _row_to_schema(self, row) -> MindLensSchema:
        """Convert database row to MindLensSchema."""
        from ...models.mind_lens import Dimension

        dimensions_data = self.deserialize_json(row['dimensions'], default=[])
        dimensions = [Dimension(**d) for d in dimensions_data]

        return MindLensSchema(
            schema_id=row['schema_id'],
            role=row['role'],
            label=row['label'],
            dimensions=dimensions,
            version=row['version'] or '0.1',
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

    def _row_to_instance(self, row) -> MindLensInstance:
        """Convert database row to MindLensInstance."""
        return MindLensInstance(
            mind_lens_id=row['mind_lens_id'],
            schema_id=row['schema_id'],
            owner_user_id=row['owner_user_id'],
            role=row['role'],
            label=row['label'],
            description=row['description'],
            values=self.deserialize_json(row['values'], default={}),
            source=self.deserialize_json(row['source']),
            version=row['version'] or '0.1',
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

    def create_lens_spec(self, lens_spec: LensSpec) -> LensSpec:
        """
        Create a new LensSpec.

        Args:
            lens_spec: LensSpec to create

        Returns:
            Created LensSpec
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO lens_specs (
                    lens_id, version, category, applies_to, inject,
                    params_schema, transformers, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lens_spec.lens_id,
                lens_spec.version,
                lens_spec.category,
                self.serialize_json(lens_spec.applies_to),
                self.serialize_json(lens_spec.inject),
                self.serialize_json(lens_spec.params_schema),
                self.serialize_json(lens_spec.transformers) if lens_spec.transformers else None,
                self.to_isoformat(lens_spec.created_at or datetime.utcnow()),
                self.to_isoformat(lens_spec.updated_at or datetime.utcnow())
            ))
            logger.info(f"Created LensSpec: {lens_spec.lens_id}")
            return lens_spec

    def get_lens_spec(self, lens_id: str) -> Optional[LensSpec]:
        """
        Get LensSpec by ID.

        Args:
            lens_id: Lens ID (may include version, e.g., "writer.hemingway@1.0.0")

        Returns:
            LensSpec or None if not found
        """
        # Extract base lens_id (without version)
        base_lens_id = lens_id.split('@')[0] if '@' in lens_id else lens_id

        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Try exact match first
            cursor.execute('SELECT * FROM lens_specs WHERE lens_id = ?', (lens_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_lens_spec(row)

            # Try base lens_id
            cursor.execute('SELECT * FROM lens_specs WHERE lens_id = ?', (base_lens_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_lens_spec(row)

            return None

    def list_lens_specs(
        self,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[LensSpec]:
        """
        List LensSpecs with filters.

        Args:
            category: Optional category filter
            limit: Maximum number of results

        Returns:
            List of LensSpecs
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    'SELECT * FROM lens_specs WHERE category = ? ORDER BY created_at DESC LIMIT ?',
                    (category, limit)
                )
            else:
                cursor.execute(
                    'SELECT * FROM lens_specs ORDER BY created_at DESC LIMIT ?',
                    (limit,)
                )
            rows = cursor.fetchall()
            return [self._row_to_lens_spec(row) for row in rows]

    def _row_to_lens_spec(self, row) -> LensSpec:
        """Convert database row to LensSpec."""
        return LensSpec(
            lens_id=row['lens_id'],
            version=row['version'],
            category=row['category'],
            applies_to=self.deserialize_json(row['applies_to'], default=[]),
            inject=self.deserialize_json(row['inject'], default={}),
            params_schema=self.deserialize_json(row['params_schema'], default={}),
            transformers=self.deserialize_json(row['transformers']) if row['transformers'] else None,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

