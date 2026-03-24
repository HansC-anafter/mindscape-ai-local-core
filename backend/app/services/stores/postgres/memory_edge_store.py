"""PostgreSQL store for memory_edges."""

from typing import Any, Dict, List

from sqlalchemy import text

from backend.app.models.memory_contract import MemoryEdge
from backend.app.services.stores.postgres_base import PostgresStoreBase


class MemoryEdgeStore(PostgresStoreBase):
    """CRUD helpers for memory_edges."""

    def create(self, edge: MemoryEdge) -> MemoryEdge:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_edges (
                        id, from_memory_id, to_memory_id, edge_type, weight,
                        valid_from, valid_to, evidence_strength, metadata, created_at
                    ) VALUES (
                        :id, :from_memory_id, :to_memory_id, :edge_type, :weight,
                        :valid_from, :valid_to, :evidence_strength, :metadata, :created_at
                    )
                    """
                ),
                {
                    "id": edge.id,
                    "from_memory_id": edge.from_memory_id,
                    "to_memory_id": edge.to_memory_id,
                    "edge_type": edge.edge_type,
                    "weight": edge.weight,
                    "valid_from": edge.valid_from,
                    "valid_to": edge.valid_to,
                    "evidence_strength": edge.evidence_strength,
                    "metadata": self.serialize_json(edge.metadata),
                    "created_at": edge.created_at,
                },
            )
        return edge

    def exists(self, *, from_memory_id: str, to_memory_id: str, edge_type: str) -> bool:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM memory_edges
                    WHERE from_memory_id = :from_memory_id
                      AND to_memory_id = :to_memory_id
                      AND edge_type = :edge_type
                    LIMIT 1
                    """
                ),
                {
                    "from_memory_id": from_memory_id,
                    "to_memory_id": to_memory_id,
                    "edge_type": edge_type,
                },
            ).fetchone()
        return row is not None

    def list_from_memory(self, from_memory_id: str) -> List[MemoryEdge]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM memory_edges
                    WHERE from_memory_id = :from_memory_id
                    ORDER BY created_at ASC
                    """
                ),
                {"from_memory_id": from_memory_id},
            ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    def _row_to_edge(self, row: Any) -> MemoryEdge:
        data: Dict[str, Any] = row._mapping if hasattr(row, "_mapping") else row
        return MemoryEdge(
            id=data["id"],
            from_memory_id=data["from_memory_id"],
            to_memory_id=data["to_memory_id"],
            edge_type=data["edge_type"],
            weight=data.get("weight"),
            valid_from=data["valid_from"],
            valid_to=data.get("valid_to"),
            evidence_strength=data.get("evidence_strength"),
            metadata=self.deserialize_json(data.get("metadata"), default={}),
            created_at=data["created_at"],
        )
