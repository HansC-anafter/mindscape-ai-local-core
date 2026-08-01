"""Workspace-scoped relation/provenance registry for Addressable Object Layer."""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional

from sqlalchemy import text

from backend.app.models.object_runtime import ObjectRef, ObjectRelationRecord
from backend.app.services.stores.postgres_base import PostgresStoreBase


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS object_relations (
    workspace_id      TEXT NOT NULL,
    relation_id       TEXT NOT NULL,
    source_uri        TEXT NOT NULL,
    relation_kind     TEXT NOT NULL,
    target_uri        TEXT NOT NULL,
    source_ref        JSONB NOT NULL,
    target_ref        JSONB NOT NULL,
    source_role       TEXT,
    target_role       TEXT,
    provenance_type   TEXT,
    provenance_id     TEXT,
    meeting_id        TEXT,
    metadata          JSONB DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, relation_id)
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_object_relations_source ON object_relations(workspace_id, source_uri, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_object_relations_target ON object_relations(workspace_id, target_uri, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_object_relations_kind ON object_relations(workspace_id, relation_kind, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_object_relations_meeting ON object_relations(workspace_id, meeting_id, updated_at DESC)",
]

_BATCH_UPSERT = text(
    """
    WITH input_rows AS (
        SELECT *
        FROM jsonb_to_recordset(CAST(:relations AS JSONB)) AS input_row (
            ordinal INTEGER,
            workspace_id TEXT,
            relation_id TEXT,
            source_uri TEXT,
            relation_kind TEXT,
            target_uri TEXT,
            source_ref JSONB,
            target_ref JSONB,
            source_role TEXT,
            target_role TEXT,
            provenance_type TEXT,
            provenance_id TEXT,
            meeting_id TEXT,
            metadata JSONB,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ
        )
    ),
    ranked_rows AS (
        SELECT
            *,
            row_number() OVER (
                PARTITION BY workspace_id, relation_id
                ORDER BY ordinal DESC
            ) AS latest_rank,
            first_value(created_at) OVER (
                PARTITION BY workspace_id, relation_id
                ORDER BY ordinal
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            ) AS first_created_at
        FROM input_rows
    ),
    latest_rows AS (
        SELECT *
        FROM ranked_rows
        WHERE latest_rank = 1
    )
    INSERT INTO object_relations (
        workspace_id, relation_id, source_uri, relation_kind,
        target_uri, source_ref, target_ref, source_role,
        target_role, provenance_type, provenance_id, meeting_id,
        metadata, created_at, updated_at
    )
    SELECT
        workspace_id, relation_id, source_uri, relation_kind,
        target_uri, source_ref, target_ref, source_role,
        target_role, provenance_type, provenance_id, meeting_id,
        metadata,
        COALESCE(first_created_at, now()),
        COALESCE(updated_at, now())
    FROM latest_rows
    ORDER BY ordinal
    ON CONFLICT (workspace_id, relation_id) DO UPDATE SET
        source_uri = EXCLUDED.source_uri,
        relation_kind = EXCLUDED.relation_kind,
        target_uri = EXCLUDED.target_uri,
        source_ref = EXCLUDED.source_ref,
        target_ref = EXCLUDED.target_ref,
        source_role = EXCLUDED.source_role,
        target_role = EXCLUDED.target_role,
        provenance_type = EXCLUDED.provenance_type,
        provenance_id = EXCLUDED.provenance_id,
        meeting_id = EXCLUDED.meeting_id,
        metadata = EXCLUDED.metadata,
        updated_at = EXCLUDED.updated_at
    """
)


class ObjectRelationRegistryStore(PostgresStoreBase):
    """Durable object relation graph used by AOL graph and provenance views."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not ObjectRelationRegistryStore._table_ensured:
            self.ensure_table()
            ObjectRelationRegistryStore._table_ensured = True

    def ensure_table(self) -> None:
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for ddl in INDEX_DDL:
                conn.execute(text(ddl))

    def upsert_many(
        self,
        workspace_id: str,
        relations: List[ObjectRelationRecord],
    ) -> int:
        if not relations:
            return 0

        payload = []
        for ordinal, relation in enumerate(relations):
            relation_id = relation.relation_id or self._build_relation_id(
                workspace_id=workspace_id,
                relation=relation,
            )
            payload.append(
                {
                    "ordinal": ordinal,
                    "workspace_id": workspace_id,
                    "relation_id": relation_id,
                    "source_uri": relation.source_ref.uri,
                    "relation_kind": relation.relation_kind,
                    "target_uri": relation.target_ref.uri,
                    "source_ref": relation.source_ref.model_dump(exclude_none=True),
                    "target_ref": relation.target_ref.model_dump(exclude_none=True),
                    "source_role": relation.source_role,
                    "target_role": relation.target_role,
                    "provenance_type": relation.provenance_type,
                    "provenance_id": relation.provenance_id,
                    "meeting_id": relation.meeting_id,
                    "metadata": relation.metadata,
                    "created_at": relation.created_at,
                    "updated_at": relation.updated_at,
                }
            )
        relations_json = self.serialize_json(payload)

        with self.transaction() as conn:
            conn.execute(_BATCH_UPSERT, {"relations": relations_json})
        return len(relations)

    def search(
        self,
        *,
        workspace_id: str,
        object_uri: Optional[str] = None,
        source_uri: Optional[str] = None,
        target_uri: Optional[str] = None,
        relation_kind: Optional[str] = None,
        meeting_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ObjectRelationRecord]:
        conditions = ["workspace_id = :workspace_id"]
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "limit": max(1, min(limit, 500)),
        }
        if object_uri:
            conditions.append("(source_uri = :object_uri OR target_uri = :object_uri)")
            params["object_uri"] = object_uri
        if source_uri:
            conditions.append("source_uri = :source_uri")
            params["source_uri"] = source_uri
        if target_uri:
            conditions.append("target_uri = :target_uri")
            params["target_uri"] = target_uri
        if relation_kind:
            conditions.append("relation_kind = :relation_kind")
            params["relation_kind"] = relation_kind
        if meeting_id:
            conditions.append("meeting_id = :meeting_id")
            params["meeting_id"] = meeting_id

        query = f"""
            SELECT *
            FROM object_relations
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC
            LIMIT :limit
        """
        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_record(row._mapping) for row in rows]

    def _build_relation_id(
        self,
        *,
        workspace_id: str,
        relation: ObjectRelationRecord,
    ) -> str:
        payload = {
            "workspace_id": workspace_id,
            "source_uri": relation.source_ref.uri,
            "relation_kind": relation.relation_kind,
            "target_uri": relation.target_ref.uri,
            "source_role": relation.source_role,
            "target_role": relation.target_role,
            "provenance_type": relation.provenance_type,
            "provenance_id": relation.provenance_id,
            "meeting_id": relation.meeting_id,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        return f"rel_{digest}"

    def _row_to_record(self, row: Any) -> ObjectRelationRecord:
        return ObjectRelationRecord(
            relation_id=row["relation_id"],
            workspace_id=row["workspace_id"],
            source_ref=ObjectRef.model_validate(
                self.deserialize_json(row.get("source_ref"), default={})
            ),
            relation_kind=row["relation_kind"],
            target_ref=ObjectRef.model_validate(
                self.deserialize_json(row.get("target_ref"), default={})
            ),
            source_role=row.get("source_role"),
            target_role=row.get("target_role"),
            provenance_type=row.get("provenance_type"),
            provenance_id=row.get("provenance_id"),
            meeting_id=row.get("meeting_id"),
            metadata=self.deserialize_json(row.get("metadata"), default={}),
            created_at=self.to_isoformat(row.get("created_at")),
            updated_at=self.to_isoformat(row.get("updated_at")),
        )
