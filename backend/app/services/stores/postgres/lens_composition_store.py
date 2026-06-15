from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

from .remaining_store_utils import _utc_now

logger = logging.getLogger(__name__)


# =================================================================================
# Lens Composition Store
# =================================================================================
class PostgresLensCompositionStore(PostgresStoreBase):
    """Postgres implementation of LensCompositionStore."""

    def create_composition(self, composition: LensComposition) -> LensComposition:
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
                    [l.model_dump() for l in composition.lens_stack]
                ),
                "fusion_strategy": composition.fusion_strategy,
                "metadata": self.serialize_json(composition.metadata),
                "created_at": composition.created_at or _utc_now(),
                "updated_at": composition.updated_at or _utc_now(),
            }
            conn.execute(query, params)
            return composition

    def get_composition(self, composition_id: str) -> Optional[LensComposition]:
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM lens_compositions WHERE composition_id = :composition_id"
            )
            row = conn.execute(query, {"composition_id": composition_id}).fetchone()
            if not row:
                return None
            return self._row_to_composition(row)

    def list_compositions(
        self, workspace_id: Optional[str] = None, limit: int = 50
    ) -> List[LensComposition]:
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

    def delete_composition(self, composition_id: str) -> bool:
        with self.transaction() as conn:
            query = text(
                "DELETE FROM lens_compositions WHERE composition_id = :composition_id"
            )
            result = conn.execute(query, {"composition_id": composition_id})
            return result.rowcount > 0

    def _row_to_composition(self, row) -> LensComposition:
        lens_stack_data = self.deserialize_json(row.lens_stack, default=[])
        lens_stack = [LensReference(**l) for l in lens_stack_data]
        return LensComposition(
            composition_id=row.composition_id,
            workspace_id=row.workspace_id,
            name=row.name,
            description=row.description,
            lens_stack=lens_stack,
            fusion_strategy=row.fusion_strategy or "priority_then_weighted",
            metadata=self.deserialize_json(row.metadata),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
