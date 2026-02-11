"""Lens Composition store for data persistence (Postgres)."""
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from ...models.lens_composition import LensComposition, LensReference

logger = logging.getLogger(__name__)


class LensCompositionStore(PostgresStoreBase):
    """Store for managing Lens Compositions (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_composition(self, composition: LensComposition) -> LensComposition:
        """Create a new composition."""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO lens_compositions (
                    composition_id, workspace_id, name, description,
                    lens_stack, fusion_strategy, metadata, created_at, updated_at
                ) VALUES (
                    :composition_id, :workspace_id, :name, :description,
                    :lens_stack, :fusion_strategy, :metadata, :created_at, :updated_at
                )
            """
            )
            params = {
                "composition_id": composition.composition_id,
                "workspace_id": composition.workspace_id,
                "name": composition.name,
                "description": composition.description,
                "lens_stack": self.serialize_json(
                    [l.dict() for l in composition.lens_stack]
                ),
                "fusion_strategy": composition.fusion_strategy,
                "metadata": self.serialize_json(composition.metadata),
                "created_at": composition.created_at or _utc_now(),
                "updated_at": composition.updated_at or _utc_now(),
            }
            conn.execute(query, params)
            logger.info(f"Created Lens Composition: {composition.composition_id}")
            return composition

    def get_composition(self, composition_id: str) -> Optional[LensComposition]:
        """Get composition by ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    "SELECT * FROM lens_compositions WHERE composition_id = :composition_id"
                ),
                {"composition_id": composition_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_composition(row)

    def update_composition(self, composition_id: str, updates: dict) -> Optional[LensComposition]:
        """Update composition."""
        if not updates:
            return self.get_composition(composition_id)

        set_clauses = []
        params = {"composition_id": composition_id}

        if "name" in updates:
            set_clauses.append("name = :name")
            params["name"] = updates["name"]

        if "description" in updates:
            set_clauses.append("description = :description")
            params["description"] = updates["description"]

        if "lens_stack" in updates:
            set_clauses.append("lens_stack = :lens_stack")
            params["lens_stack"] = self.serialize_json(
                [l.dict() if hasattr(l, "dict") else l for l in updates["lens_stack"]]
            )

        if "fusion_strategy" in updates:
            set_clauses.append("fusion_strategy = :fusion_strategy")
            params["fusion_strategy"] = updates["fusion_strategy"]

        if "metadata" in updates:
            set_clauses.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(updates["metadata"])

        if not set_clauses:
            return self.get_composition(composition_id)

        set_clauses.append("updated_at = :updated_at")
        params["updated_at"] = _utc_now()

        with self.transaction() as conn:
            result = conn.execute(
                text(
                    f"UPDATE lens_compositions SET {', '.join(set_clauses)} WHERE composition_id = :composition_id"
                ),
                params,
            )
            if result.rowcount == 0:
                return None

        logger.info(f"Updated Lens Composition: {composition_id}")
        return self.get_composition(composition_id)

    def delete_composition(self, composition_id: str) -> bool:
        """Delete composition."""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM lens_compositions WHERE composition_id = :composition_id"
                ),
                {"composition_id": composition_id},
            )
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"Deleted Lens Composition: {composition_id}")
            return deleted

    def list_compositions(
        self, workspace_id: Optional[str] = None, limit: int = 50
    ) -> List[LensComposition]:
        """List compositions with filters."""
        with self.get_connection() as conn:
            query_str = "SELECT * FROM lens_compositions"
            params = {"limit": limit}
            if workspace_id:
                query_str += " WHERE workspace_id = :workspace_id ORDER BY updated_at DESC LIMIT :limit"
                params["workspace_id"] = workspace_id
            else:
                query_str += " ORDER BY updated_at DESC LIMIT :limit"

            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_composition(row) for row in rows]

    def _row_to_composition(self, row) -> LensComposition:
        """Convert database row to LensComposition."""
        data = row._mapping if hasattr(row, "_mapping") else row
        lens_stack_data = self.deserialize_json(data["lens_stack"], default=[])
        lens_stack = [LensReference(**l) for l in lens_stack_data]

        return LensComposition(
            composition_id=data["composition_id"],
            workspace_id=data["workspace_id"],
            name=data["name"],
            description=data["description"],
            lens_stack=lens_stack,
            fusion_strategy=data["fusion_strategy"] or "priority_then_weighted",
            metadata=self.deserialize_json(data["metadata"]),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
