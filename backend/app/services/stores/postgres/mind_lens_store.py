"""Postgres adaptation of MindLensStore."""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.mind_lens import MindLensSchema, MindLensInstance, LensSpec
from ..mind_lens_store import MindLensStore

logger = logging.getLogger(__name__)


class PostgresMindLensStore(PostgresStoreBase):
    """Postgres implementation of MindLensStore."""

    # Note: We inherit from PostgresStoreBase for implementation,
    # but we should ensure we satisfy the MindLensStore public DOM.
    # Since Python is duck-typed, as long as methods match, we are good.
    # (The original MindLensStore inherits from StoreBase)

    def create_schema(self, schema: MindLensSchema) -> MindLensSchema:
        """Create a new Mind Lens schema."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO mind_lens_schemas (
                    schema_id, role, label, dimensions, version, created_at, updated_at
                ) VALUES (
                    :schema_id, :role, :label, :dimensions, :version, :created_at, :updated_at
                )
            """
            )
            params = {
                "schema_id": schema.schema_id,
                "role": schema.role,
                "label": schema.label,
                "dimensions": self.serialize_json(
                    [d.dict() for d in schema.dimensions]
                ),
                "version": schema.version,
                "created_at": schema.created_at or _utc_now(),
                "updated_at": schema.updated_at or _utc_now(),
            }
            conn.execute(query, params)
            logger.info(f"Created Mind Lens schema: {schema.schema_id}")
            return schema

    def get_schema(self, schema_id: str) -> Optional[MindLensSchema]:
        """Get schema by ID."""
        with self.get_connection() as conn:
            query = text("SELECT * FROM mind_lens_schemas WHERE schema_id = :schema_id")
            result = conn.execute(query, {"schema_id": schema_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_schema(row)

    def get_schema_by_role(self, role: str) -> Optional[MindLensSchema]:
        """Get schema by role."""
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM mind_lens_schemas WHERE role = :role ORDER BY version DESC LIMIT 1"
            )
            result = conn.execute(query, {"role": role})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_schema(row)

    def create_instance(self, instance: MindLensInstance) -> MindLensInstance:
        """Create a new Mind Lens instance."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO mind_lens_instances (
                    mind_lens_id, schema_id, owner_user_id, role, label, description,
                    "values", source, version, created_at, updated_at
                ) VALUES (
                    :mind_lens_id, :schema_id, :owner_user_id, :role, :label, :description,
                    :values, :source, :version, :created_at, :updated_at
                )
            """
            )
            params = {
                "mind_lens_id": instance.mind_lens_id,
                "schema_id": instance.schema_id,
                "owner_user_id": instance.owner_user_id,
                "role": instance.role,
                "label": instance.label,
                "description": instance.description,
                "values": self.serialize_json(instance.values),
                "source": self.serialize_json(instance.source),
                "version": instance.version,
                "created_at": instance.created_at or _utc_now(),
                "updated_at": instance.updated_at or _utc_now(),
            }
            conn.execute(query, params)
            logger.info(f"Created Mind Lens instance: {instance.mind_lens_id}")
            return instance

    def get_instance(self, instance_id: str) -> Optional[MindLensInstance]:
        """Get instance by ID."""
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM mind_lens_instances WHERE mind_lens_id = :instance_id"
            )
            result = conn.execute(query, {"instance_id": instance_id})
            row = result.fetchone()
            if not row:
                return None
            return self._row_to_instance(row)

    def list_instances(
        self,
        owner_user_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50,
    ) -> List[MindLensInstance]:
        """List instances with filters."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM mind_lens_instances WHERE 1=1"
            params = {"limit": limit}

            if owner_user_id:
                query_str += " AND owner_user_id = :owner_user_id"
                params["owner_user_id"] = owner_user_id

            if role:
                query_str += " AND role = :role"
                params["role"] = role

            query_str += " ORDER BY updated_at DESC LIMIT :limit"

            result = conn.execute(text(query_str), params)
            rows = result.fetchall()
            return [self._row_to_instance(row) for row in rows]

    def update_instance(
        self, instance_id: str, updates: dict
    ) -> Optional[MindLensInstance]:
        """Update instance."""
        with self.transaction() as conn:
            set_clauses = []
            params = {"instance_id": instance_id}

            if "label" in updates:
                set_clauses.append("label = :label")
                params["label"] = updates["label"]

            if "description" in updates:
                set_clauses.append("description = :description")
                params["description"] = updates["description"]

            if "values" in updates:
                set_clauses.append('"values" = :values')
                params["values"] = self.serialize_json(updates["values"])

            if "source" in updates:
                set_clauses.append("source = :source")
                params["source"] = self.serialize_json(updates["source"])

            if not set_clauses:
                return self.get_instance(instance_id)

            set_clauses.append("updated_at = :updated_at")
            params["updated_at"] = _utc_now()

            query = text(
                f'UPDATE mind_lens_instances SET {", ".join(set_clauses)} WHERE mind_lens_id = :instance_id'
            )
            result = conn.execute(query, params)

            if result.rowcount == 0:
                return None

            logger.info(f"Updated Mind Lens instance: {instance_id}")

            # Re-fetch using the SAME connection to see uncommitted changes (before commit)
            query_get = text(
                "SELECT * FROM mind_lens_instances WHERE mind_lens_id = :instance_id"
            )
            result_get = conn.execute(query_get, {"instance_id": instance_id})
            row = result_get.fetchone()
            if not row:
                return None
            return self._row_to_instance(row)

    def create_lens_spec(self, lens_spec: LensSpec) -> LensSpec:
        """Create a new LensSpec."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO lens_specs (
                    lens_id, version, category, applies_to, inject,
                    params_schema, transformers, created_at, updated_at
                ) VALUES (
                    :lens_id, :version, :category, :applies_to, :inject,
                    :params_schema, :transformers, :created_at, :updated_at
                )
            """
            )
            params = {
                "lens_id": lens_spec.lens_id,
                "version": lens_spec.version,
                "category": lens_spec.category,
                "applies_to": self.serialize_json(lens_spec.applies_to),
                "inject": self.serialize_json(lens_spec.inject),
                "params_schema": self.serialize_json(lens_spec.params_schema),
                "transformers": (
                    self.serialize_json(lens_spec.transformers)
                    if lens_spec.transformers
                    else None
                ),
                "created_at": lens_spec.created_at or _utc_now(),
                "updated_at": lens_spec.updated_at or _utc_now(),
            }
            conn.execute(query, params)
            logger.info(f"Created LensSpec: {lens_spec.lens_id}")
            return lens_spec

    def get_lens_spec(self, lens_id: str) -> Optional[LensSpec]:
        """Get LensSpec by ID."""
        base_lens_id = lens_id.split("@")[0] if "@" in lens_id else lens_id

        with self.get_connection() as conn:
            # Try exact match first
            query = text("SELECT * FROM lens_specs WHERE lens_id = :lens_id")
            result = conn.execute(query, {"lens_id": lens_id})
            row = result.fetchone()
            if row:
                return self._row_to_lens_spec(row)

            # Try base lens_id
            query = text("SELECT * FROM lens_specs WHERE lens_id = :base_lens_id")
            result = conn.execute(query, {"base_lens_id": base_lens_id})
            row = result.fetchone()
            if row:
                return self._row_to_lens_spec(row)

            return None

    def list_lens_specs(
        self, category: Optional[str] = None, limit: int = 50
    ) -> List[LensSpec]:
        """List LensSpecs with filters."""
        with self.get_connection() as conn:
            params = {"limit": limit}
            if category:
                query = text(
                    "SELECT * FROM lens_specs WHERE category = :category ORDER BY created_at DESC LIMIT :limit"
                )
                params["category"] = category
            else:
                query = text(
                    "SELECT * FROM lens_specs ORDER BY created_at DESC LIMIT :limit"
                )

            result = conn.execute(query, params)
            rows = result.fetchall()
            return [self._row_to_lens_spec(row) for row in rows]

    def _row_to_schema(self, row) -> MindLensSchema:
        """Convert database row to MindLensSchema."""
        from app.models.mind_lens import Dimension
        from app.models.mind_lens import MindLensSchema

        # In SQLAlchemy result (from psycopg2), JSON columns are already deserialized to dict/list
        # But PostgresStoreBase.deserialize_json handles both string and dict.
        # Since we use JSONB column type in Postgres, psycopg2 returns python objects.
        # However, if we inserted as string via serialize_json, psycopg2 usually adapts it.
        # Check if deserialization is needed.
        # The base `deserialize_json` checks `isinstance(data, (dict, list))` and returns as is.
        # So it is safe to use.

        # Access by column name using _mapping for SQLAlchemy results
        # row is a Row object. row.dimensions works if text() query was simple
        # or use row._mapping['dimensions']

        dimensions_data = self.deserialize_json(row.dimensions, default=[])
        dimensions = [Dimension(**d) for d in dimensions_data]

        return MindLensSchema(
            schema_id=row.schema_id,
            role=row.role,
            label=row.label,
            dimensions=dimensions,
            version=row.version or "0.1",
            created_at=row.created_at,  # SQLAlchemy returns datetime objects for timestamp columns
            updated_at=row.updated_at,
        )

    def _row_to_instance(self, row) -> MindLensInstance:
        """Convert database row to MindLensInstance."""
        return MindLensInstance(
            mind_lens_id=row.mind_lens_id,
            schema_id=row.schema_id,
            owner_user_id=row.owner_user_id,
            role=row.role,
            label=row.label,
            description=row.description,
            values=self.deserialize_json(row.values, default={}),
            source=self.deserialize_json(row.source),
            version=row.version or "0.1",
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _row_to_lens_spec(self, row) -> LensSpec:
        """Convert database row to LensSpec."""
        return LensSpec(
            lens_id=row.lens_id,
            version=row.version,
            category=row.category,
            applies_to=self.deserialize_json(row.applies_to, default=[]),
            inject=self.deserialize_json(row.inject, default={}),
            params_schema=self.deserialize_json(row.params_schema, default={}),
            transformers=(
                self.deserialize_json(row.transformers) if row.transformers else None
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
