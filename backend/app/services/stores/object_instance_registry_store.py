"""Workspace-scoped read model for concrete addressable object instances."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import text

from backend.app.models.object_runtime import ObjectInstanceRecord, ObjectRef
from backend.app.services.stores.postgres_base import PostgresStoreBase


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS object_instances (
    workspace_id        TEXT NOT NULL,
    uri                 TEXT NOT NULL,
    owner_pack          TEXT NOT NULL,
    object_kind         TEXT NOT NULL,
    object_id           TEXT NOT NULL,
    version             TEXT,
    selector            JSONB,
    source_surface      TEXT,
    title               TEXT NOT NULL,
    subtitle            TEXT,
    summary_text        TEXT,
    labels              JSONB DEFAULT '[]'::jsonb,
    thumbnail_ref       TEXT,
    owner_surface_url   TEXT,
    mention_tokens      JSONB DEFAULT '[]'::jsonb,
    mention_text        TEXT DEFAULT '',
    search_text         TEXT DEFAULT '',
    affordance_verbs    JSONB DEFAULT '[]'::jsonb,
    stale               BOOLEAN DEFAULT FALSE,
    metadata            JSONB DEFAULT '{}'::jsonb,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, uri)
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_object_instances_workspace_kind ON object_instances(workspace_id, owner_pack, object_kind)",
    "CREATE INDEX IF NOT EXISTS idx_object_instances_workspace_updated ON object_instances(workspace_id, updated_at DESC)",
]


class ObjectInstanceRegistryStore(PostgresStoreBase):
    """Durable object instance registry used by search and mention completion."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not ObjectInstanceRegistryStore._table_ensured:
            self.ensure_table()
            ObjectInstanceRegistryStore._table_ensured = True

    def ensure_table(self) -> None:
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for ddl in INDEX_DDL:
                conn.execute(text(ddl))

    def upsert_many(
        self,
        workspace_id: str,
        records: List[ObjectInstanceRecord],
    ) -> int:
        if not records:
            return 0

        with self.transaction() as conn:
            for record in records:
                ref = record.ref
                search_text = self._build_search_text(record)
                conn.execute(
                    text(
                        """
                        INSERT INTO object_instances (
                            workspace_id, uri, owner_pack, object_kind, object_id,
                            version, selector, source_surface,
                            title, subtitle, summary_text, labels, thumbnail_ref,
                            owner_surface_url, mention_tokens, mention_text,
                            search_text, affordance_verbs, stale, metadata, updated_at
                        ) VALUES (
                            :workspace_id, :uri, :owner_pack, :object_kind, :object_id,
                            :version, CAST(:selector AS JSONB), :source_surface,
                            :title, :subtitle, :summary_text, CAST(:labels AS JSONB),
                            :thumbnail_ref, :owner_surface_url,
                            CAST(:mention_tokens AS JSONB), :mention_text,
                            :search_text, CAST(:affordance_verbs AS JSONB),
                            :stale, CAST(:metadata AS JSONB),
                            COALESCE(CAST(:updated_at AS TIMESTAMPTZ), now())
                        )
                        ON CONFLICT (workspace_id, uri) DO UPDATE SET
                            owner_pack = EXCLUDED.owner_pack,
                            object_kind = EXCLUDED.object_kind,
                            object_id = EXCLUDED.object_id,
                            version = EXCLUDED.version,
                            selector = EXCLUDED.selector,
                            source_surface = EXCLUDED.source_surface,
                            title = EXCLUDED.title,
                            subtitle = EXCLUDED.subtitle,
                            summary_text = EXCLUDED.summary_text,
                            labels = EXCLUDED.labels,
                            thumbnail_ref = EXCLUDED.thumbnail_ref,
                            owner_surface_url = EXCLUDED.owner_surface_url,
                            mention_tokens = EXCLUDED.mention_tokens,
                            mention_text = EXCLUDED.mention_text,
                            search_text = EXCLUDED.search_text,
                            affordance_verbs = EXCLUDED.affordance_verbs,
                            stale = EXCLUDED.stale,
                            metadata = EXCLUDED.metadata,
                            updated_at = EXCLUDED.updated_at
                        """
                    ),
                    {
                        "workspace_id": workspace_id,
                        "uri": ref.uri,
                        "owner_pack": ref.owner_pack,
                        "object_kind": ref.object_kind,
                        "object_id": ref.object_id,
                        "version": ref.version,
                        "selector": self.serialize_json(ref.selector),
                        "source_surface": ref.source_surface,
                        "title": record.title,
                        "subtitle": record.subtitle,
                        "summary_text": record.summary_text,
                        "labels": self.serialize_json(record.labels),
                        "thumbnail_ref": record.thumbnail_ref,
                        "owner_surface_url": record.owner_surface_url,
                        "mention_tokens": self.serialize_json(record.mention_tokens),
                        "mention_text": record.mention_text,
                        "search_text": search_text,
                        "affordance_verbs": self.serialize_json(record.affordance_verbs),
                        "stale": record.stale,
                        "metadata": self.serialize_json(record.metadata),
                        "updated_at": record.updated_at,
                    },
                )
        return len(records)

    def search(
        self,
        *,
        workspace_id: str,
        query: str = "",
        owner_pack: Optional[str] = None,
        object_kind: Optional[str] = None,
        limit: int = 20,
    ) -> List[ObjectInstanceRecord]:
        normalized_query = query.strip()
        conditions = ["workspace_id = :workspace_id"]
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "limit": max(1, min(limit, 100)),
        }

        if owner_pack:
            conditions.append("owner_pack = :owner_pack")
            params["owner_pack"] = owner_pack
        if object_kind:
            conditions.append("object_kind = :object_kind")
            params["object_kind"] = object_kind
        if normalized_query:
            conditions.append(
                """
                (
                    search_text ILIKE :query_pattern
                    OR mention_text ILIKE :query_pattern
                    OR title ILIKE :query_pattern
                    OR object_id ILIKE :query_pattern
                    OR uri ILIKE :query_pattern
                )
                """
            )
            params["query_pattern"] = f"%{normalized_query}%"

        sql = f"""
            SELECT *
            FROM object_instances
            WHERE {' AND '.join(conditions)}
            ORDER BY stale ASC, updated_at DESC
            LIMIT :limit
        """
        with self.get_connection() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [self._row_to_record(row._mapping) for row in rows]

    def get_by_uri(
        self,
        *,
        workspace_id: str,
        uri: str,
    ) -> Optional[ObjectInstanceRecord]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM object_instances
                    WHERE workspace_id = :workspace_id
                      AND uri = :uri
                    LIMIT 1
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "uri": uri,
                },
            ).fetchone()
        return self._row_to_record(row._mapping) if row else None

    def _row_to_record(self, row: Any) -> ObjectInstanceRecord:
        selector = self.deserialize_json(row.get("selector"), default=None)
        ref = ObjectRef(
            uri=row["uri"],
            owner_pack=row["owner_pack"],
            object_kind=row["object_kind"],
            object_id=row["object_id"],
            workspace_id=row["workspace_id"],
            version=row.get("version"),
            selector=selector,
            source_surface=row.get("source_surface"),
        )
        return ObjectInstanceRecord(
            ref=ref,
            title=row["title"],
            subtitle=row.get("subtitle"),
            summary_text=row.get("summary_text"),
            labels=self.deserialize_json(row.get("labels"), default=[]),
            thumbnail_ref=row.get("thumbnail_ref"),
            owner_surface_url=row.get("owner_surface_url"),
            mention_tokens=self.deserialize_json(row.get("mention_tokens"), default=[]),
            mention_text=row.get("mention_text") or "",
            search_text=row.get("search_text") or "",
            affordance_verbs=self.deserialize_json(
                row.get("affordance_verbs"),
                default=[],
            ),
            stale=bool(row.get("stale")),
            metadata=self.deserialize_json(row.get("metadata"), default={}),
            updated_at=self.to_isoformat(row.get("updated_at")),
        )

    @staticmethod
    def _build_search_text(record: ObjectInstanceRecord) -> str:
        if record.search_text.strip():
            return record.search_text.strip()
        parts = [
            record.title,
            record.subtitle or "",
            record.summary_text or "",
            record.ref.uri,
            record.ref.object_id,
            record.ref.object_kind,
            record.ref.owner_pack,
            record.mention_text,
            " ".join(record.labels),
            " ".join(record.mention_tokens),
            " ".join(record.affordance_verbs),
        ]
        return " ".join(part for part in parts if part).strip()
