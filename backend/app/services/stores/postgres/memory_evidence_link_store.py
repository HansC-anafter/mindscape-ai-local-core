"""PostgreSQL store for memory_evidence_links."""

from typing import Any, Dict, List

from sqlalchemy import text

from backend.app.models.memory_contract import MemoryEvidenceLink
from backend.app.services.stores.postgres_base import PostgresStoreBase


class MemoryEvidenceLinkStore(PostgresStoreBase):
    """CRUD helpers for memory_evidence_links."""

    def create(self, link: MemoryEvidenceLink) -> MemoryEvidenceLink:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_evidence_links (
                        id, memory_item_id, evidence_type, evidence_id,
                        link_role, excerpt, confidence, metadata, created_at
                    ) VALUES (
                        :id, :memory_item_id, :evidence_type, :evidence_id,
                        :link_role, :excerpt, :confidence, :metadata, :created_at
                    )
                    """
                ),
                {
                    "id": link.id,
                    "memory_item_id": link.memory_item_id,
                    "evidence_type": link.evidence_type,
                    "evidence_id": link.evidence_id,
                    "link_role": link.link_role,
                    "excerpt": link.excerpt,
                    "confidence": link.confidence,
                    "metadata": self.serialize_json(link.metadata),
                    "created_at": link.created_at,
                },
            )
        return link

    def exists(
        self,
        *,
        memory_item_id: str,
        evidence_type: str,
        evidence_id: str,
        link_role: str,
    ) -> bool:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1
                    FROM memory_evidence_links
                    WHERE memory_item_id = :memory_item_id
                      AND evidence_type = :evidence_type
                      AND evidence_id = :evidence_id
                      AND link_role = :link_role
                    LIMIT 1
                    """
                ),
                {
                    "memory_item_id": memory_item_id,
                    "evidence_type": evidence_type,
                    "evidence_id": evidence_id,
                    "link_role": link_role,
                },
            ).fetchone()
        return row is not None

    def list_by_memory_item(self, memory_item_id: str) -> List[MemoryEvidenceLink]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM memory_evidence_links
                    WHERE memory_item_id = :memory_item_id
                    ORDER BY created_at ASC
                    """
                ),
                {"memory_item_id": memory_item_id},
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def _row_to_link(self, row: Any) -> MemoryEvidenceLink:
        data: Dict[str, Any] = row._mapping if hasattr(row, "_mapping") else row
        return MemoryEvidenceLink(
            id=data["id"],
            memory_item_id=data["memory_item_id"],
            evidence_type=data["evidence_type"],
            evidence_id=data["evidence_id"],
            link_role=data["link_role"],
            excerpt=data.get("excerpt"),
            confidence=data.get("confidence"),
            metadata=self.deserialize_json(data.get("metadata"), default={}),
            created_at=data["created_at"],
        )
