"""PostgreSQL store for canonical memory_items."""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.memory_contract import MemoryItem
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class MemoryItemStore(PostgresStoreBase):
    """CRUD helpers for canonical memory_items."""

    def create(self, item: MemoryItem) -> MemoryItem:
        query = text(
            """
            INSERT INTO memory_items (
                id, kind, layer, scope, subject_type, subject_id,
                context_type, context_id, title, claim, summary,
                salience, confidence, verification_status, lifecycle_status,
                valid_from, valid_to, observed_at, last_confirmed_at, last_used_at,
                update_mode, supersedes_memory_id, created_by_pipeline,
                created_from_run_id, metadata, created_at, updated_at
            ) VALUES (
                :id, :kind, :layer, :scope, :subject_type, :subject_id,
                :context_type, :context_id, :title, :claim, :summary,
                :salience, :confidence, :verification_status, :lifecycle_status,
                :valid_from, :valid_to, :observed_at, :last_confirmed_at, :last_used_at,
                :update_mode, :supersedes_memory_id, :created_by_pipeline,
                :created_from_run_id, :metadata, :created_at, :updated_at
            )
            """
        )
        with self.transaction() as conn:
            conn.execute(
                query,
                {
                    "id": item.id,
                    "kind": item.kind,
                    "layer": item.layer,
                    "scope": item.scope,
                    "subject_type": item.subject_type,
                    "subject_id": item.subject_id,
                    "context_type": item.context_type,
                    "context_id": item.context_id,
                    "title": item.title,
                    "claim": item.claim,
                    "summary": item.summary,
                    "salience": item.salience,
                    "confidence": item.confidence,
                    "verification_status": item.verification_status,
                    "lifecycle_status": item.lifecycle_status,
                    "valid_from": item.valid_from,
                    "valid_to": item.valid_to,
                    "observed_at": item.observed_at,
                    "last_confirmed_at": item.last_confirmed_at,
                    "last_used_at": item.last_used_at,
                    "update_mode": item.update_mode,
                    "supersedes_memory_id": item.supersedes_memory_id,
                    "created_by_pipeline": item.created_by_pipeline,
                    "created_from_run_id": item.created_from_run_id,
                    "metadata": self.serialize_json(item.metadata),
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                },
            )
        return item

    def get(self, item_id: str) -> Optional[MemoryItem]:
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM memory_items WHERE id = :id"),
                {"id": item_id},
            ).fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def find_by_subject(
        self,
        *,
        kind: str,
        subject_type: str,
        subject_id: str,
        context_type: str = "",
        context_id: str = "",
    ) -> Optional[MemoryItem]:
        query = text(
            """
            SELECT * FROM memory_items
            WHERE kind = :kind
              AND subject_type = :subject_type
              AND subject_id = :subject_id
              AND context_type = :context_type
              AND context_id = :context_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        with self.get_connection() as conn:
            row = conn.execute(
                query,
                {
                    "kind": kind,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "context_type": context_type,
                    "context_id": context_id,
                },
            ).fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def list_for_context(
        self,
        *,
        context_type: str,
        context_id: str,
        layer: Optional[str] = None,
        kind: Optional[str] = None,
        lifecycle_statuses: Optional[List[str]] = None,
        verification_statuses: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[MemoryItem]:
        clauses = [
            "context_type = :context_type",
            "context_id = :context_id",
        ]
        params: Dict[str, Any] = {
            "context_type": context_type,
            "context_id": context_id,
            "limit": limit,
        }

        if layer:
            clauses.append("layer = :layer")
            params["layer"] = layer

        if kind:
            clauses.append("kind = :kind")
            params["kind"] = kind

        if lifecycle_statuses:
            placeholders = []
            for idx, status in enumerate(lifecycle_statuses):
                key = f"lifecycle_status_{idx}"
                params[key] = status
                placeholders.append(f":{key}")
            clauses.append(f"lifecycle_status IN ({', '.join(placeholders)})")

        if verification_statuses:
            placeholders = []
            for idx, status in enumerate(verification_statuses):
                key = f"verification_status_{idx}"
                params[key] = status
                placeholders.append(f":{key}")
            clauses.append(f"verification_status IN ({', '.join(placeholders)})")

        query = text(
            f"""
            SELECT * FROM memory_items
            WHERE {' AND '.join(clauses)}
            ORDER BY salience DESC, observed_at DESC, created_at DESC
            LIMIT :limit
            """
        )
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_item(row) for row in rows]

    def touch_last_used(self, item_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE memory_items
                    SET last_used_at = now(), updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": item_id},
            )

    def update(self, item: MemoryItem) -> MemoryItem:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE memory_items
                    SET kind = :kind,
                        layer = :layer,
                        scope = :scope,
                        subject_type = :subject_type,
                        subject_id = :subject_id,
                        context_type = :context_type,
                        context_id = :context_id,
                        title = :title,
                        claim = :claim,
                        summary = :summary,
                        salience = :salience,
                        confidence = :confidence,
                        verification_status = :verification_status,
                        lifecycle_status = :lifecycle_status,
                        valid_from = :valid_from,
                        valid_to = :valid_to,
                        observed_at = :observed_at,
                        last_confirmed_at = :last_confirmed_at,
                        last_used_at = :last_used_at,
                        update_mode = :update_mode,
                        supersedes_memory_id = :supersedes_memory_id,
                        created_by_pipeline = :created_by_pipeline,
                        created_from_run_id = :created_from_run_id,
                        metadata = :metadata,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": item.id,
                    "kind": item.kind,
                    "layer": item.layer,
                    "scope": item.scope,
                    "subject_type": item.subject_type,
                    "subject_id": item.subject_id,
                    "context_type": item.context_type,
                    "context_id": item.context_id,
                    "title": item.title,
                    "claim": item.claim,
                    "summary": item.summary,
                    "salience": item.salience,
                    "confidence": item.confidence,
                    "verification_status": item.verification_status,
                    "lifecycle_status": item.lifecycle_status,
                    "valid_from": item.valid_from,
                    "valid_to": item.valid_to,
                    "observed_at": item.observed_at,
                    "last_confirmed_at": item.last_confirmed_at,
                    "last_used_at": item.last_used_at,
                    "update_mode": item.update_mode,
                    "supersedes_memory_id": item.supersedes_memory_id,
                    "created_by_pipeline": item.created_by_pipeline,
                    "created_from_run_id": item.created_from_run_id,
                    "metadata": self.serialize_json(item.metadata),
                    "updated_at": item.updated_at,
                },
            )
        return item

    def _row_to_item(self, row: Any) -> MemoryItem:
        data: Dict[str, Any] = row._mapping if hasattr(row, "_mapping") else row
        return MemoryItem(
            id=data["id"],
            kind=data["kind"],
            layer=data["layer"],
            scope=data["scope"],
            subject_type=data["subject_type"],
            subject_id=data["subject_id"],
            context_type=data["context_type"],
            context_id=data["context_id"],
            title=data["title"],
            claim=data["claim"],
            summary=data["summary"],
            salience=data["salience"],
            confidence=data["confidence"],
            verification_status=data["verification_status"],
            lifecycle_status=data["lifecycle_status"],
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            observed_at=data["observed_at"],
            last_confirmed_at=data.get("last_confirmed_at"),
            last_used_at=data.get("last_used_at"),
            update_mode=data.get("update_mode"),
            supersedes_memory_id=data.get("supersedes_memory_id"),
            created_by_pipeline=data["created_by_pipeline"],
            created_from_run_id=data.get("created_from_run_id"),
            metadata=self.deserialize_json(data.get("metadata"), default={}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
