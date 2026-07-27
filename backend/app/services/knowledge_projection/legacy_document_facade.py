"""Authorized compatibility seam for legacy document ingestion surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from psycopg2.extras import RealDictCursor

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedIndexRevokeResult,
    AuthorizedIndexWriteResult,
    AuthorizedKnowledgeIndexStore,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeGrant,
    KnowledgeResourceIdentity,
    PrincipalRef,
    RetrievalAccessContext,
    set_local_knowledge_context,
)
from backend.app.services.vector_search import VectorSearchService

from .retrievable.canonical_json import canonical_sha256
from .retrievable.document_adapter import compile_document_projection


@dataclass(frozen=True)
class LegacyDocumentChunk:
    content: str
    title: str
    metadata: Mapping[str, Any]
    embedding: tuple[float, ...] = ()


class AuthorizedLegacyDocumentFacade:
    """Preserve legacy product paths without preserving raw vector DML."""

    def __init__(
        self,
        *,
        vector_service: VectorSearchService | None = None,
        index_store: AuthorizedKnowledgeIndexStore | None = None,
    ) -> None:
        self._vector_service = vector_service or VectorSearchService()
        self._connection_factory = self._vector_service._get_connection
        self._index_store = index_store or AuthorizedKnowledgeIndexStore(
            self._connection_factory
        )

    async def replace_document(
        self,
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
        owner_capability_code: str,
        source_app: str,
        source_id: str,
        doc_type: str,
        chunks: Iterable[LegacyDocumentChunk],
        source_revision: str | None = None,
        owner_scope_type: str = "workspace",
        owner_scope_id: str | None = None,
        projection_records: Iterable[Mapping[str, Any]] = (),
        owner_declared_graph: Mapping[str, Any] | None = None,
    ) -> AuthorizedIndexWriteResult:
        scope_id = owner_scope_id or workspace_id
        self._require_project(
            access_context,
            scope_type=owner_scope_type,
            scope_id=scope_id,
        )
        prepared = tuple(chunks)
        if not prepared:
            raise ValueError("legacy_document_chunks_required")
        revision = source_revision or canonical_sha256(
            {
                "source_app": source_app,
                "source_id": source_id,
                "chunks": [
                    {
                        "content": chunk.content,
                        "title": chunk.title,
                        "metadata": dict(chunk.metadata),
                    }
                    for chunk in prepared
                ],
            }
        )
        checksum = canonical_sha256(
            [chunk.content for chunk in prepared]
        )
        document_id = f"{source_app}:{source_id}"
        records = []
        for index, chunk in enumerate(prepared):
            embedding = list(chunk.embedding)
            model_name = ""
            if not embedding:
                embedding, model_name = (
                    await self._vector_service._generate_embedding_with_model(
                        chunk.content,
                        is_query=False,
                    )
                )
                model_name = str(model_name or "unknown")
            else:
                model_name = str(
                    chunk.metadata.get("embedding_model")
                    or "caller-provided"
                )
            if not embedding:
                raise RuntimeError("legacy_document_embedding_unavailable")
            metadata = {
                **dict(chunk.metadata),
                "workspace_id": workspace_id,
                "document_id": document_id,
                "revision_id": revision,
                "checksum": checksum,
                "chunk_id": str(
                    chunk.metadata.get("chunk_id") or f"chunk-{index}"
                ),
                "active": True,
                "embedding_model": model_name,
                "pipeline_version": "legacy-document-compatibility.v1",
            }
            records.append(
                {
                    "source_id": f"{document_id}:{revision}:{index}",
                    "doc_type": doc_type,
                    "title": chunk.title,
                    "content": chunk.content,
                    "embedding": embedding,
                    "metadata": metadata,
                }
            )
        payload, documents = compile_document_projection(
            workspace_id=workspace_id,
            document_id=document_id,
            revision_id=revision,
            records=records,
            projection_records=projection_records,
            owner_declared_graph=owner_declared_graph,
        )
        initial_grants: tuple[KnowledgeGrant, ...] = ()
        if owner_scope_type == "group":
            initial_grants = (
                KnowledgeGrant(
                    principal=PrincipalRef(
                        "group_role",
                        f"{scope_id}:owner",
                    ),
                    relation="owner",
                ),
                KnowledgeGrant(
                    principal=PrincipalRef(
                        "group_role",
                        f"{scope_id}:member",
                    ),
                    relation="reader",
                ),
            )
        return self._index_store.replace_projection(
            access_context=access_context,
            identity=self._identity(
                access_context=access_context,
                workspace_id=workspace_id,
                owner_capability_code=owner_capability_code,
                source_app=source_app,
                source_id=source_id,
                source_revision=revision,
                owner_scope_type=owner_scope_type,
                owner_scope_id=scope_id,
            ),
            payload=payload,
            documents=documents,
            initial_grants=initial_grants,
        )

    def active_revision(
        self,
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
        owner_capability_code: str,
        source_app: str,
        source_id: str,
    ) -> str | None:
        rows = self.list_documents(
            access_context=access_context,
            workspace_id=workspace_id,
            owner_capability_code=owner_capability_code,
            source_app=source_app,
            source_ids=(source_id,),
            limit=1,
        )
        return str(rows[0]["source_revision"]) if rows else None

    def revoke_document(
        self,
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
        owner_capability_code: str,
        source_app: str,
        source_id: str,
    ) -> AuthorizedIndexRevokeResult | None:
        self._require_project(access_context, workspace_id)
        revision = self.active_revision(
            access_context=access_context,
            workspace_id=workspace_id,
            owner_capability_code=owner_capability_code,
            source_app=source_app,
            source_id=source_id,
        )
        if revision is None:
            return None
        return self._index_store.revoke_projection(
            access_context=access_context,
            identity=self._identity(
                access_context=access_context,
                workspace_id=workspace_id,
                owner_capability_code=owner_capability_code,
                source_app=source_app,
                source_id=source_id,
                source_revision=revision,
            ),
        )

    def list_documents(
        self,
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
        owner_capability_code: str | None = None,
        source_app: str | None = None,
        source_ids: tuple[str, ...] = (),
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not (
            access_context.has_permission(
                "knowledge.read",
                scope_type="workspace",
                scope_id=workspace_id,
            )
            or access_context.has_permission(
                "knowledge.project",
                scope_type="workspace",
                scope_id=workspace_id,
            )
        ):
            raise PermissionError("legacy_document_read_permission_required")
        bounded_limit = max(1, min(int(limit), 200))
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            set_local_knowledge_context(cursor, access_context)
            cursor.execute(
                """
                SELECT
                    resource.knowledge_resource_id,
                    resource.owner_capability_code,
                    resource.source_app,
                    resource.source_id,
                    resource.source_revision,
                    resource.updated_at,
                    projection.projection_revision_id,
                    projection.status,
                    COUNT(document.id)::integer AS chunk_count,
                    MAX(document.title) AS title,
                    MAX(document.doc_type) AS doc_type,
                    (ARRAY_AGG(
                        document.metadata ORDER BY document.id
                    ))[1] AS metadata,
                    MAX(document.last_synced_at) AS last_synced_at
                FROM knowledge_resources AS resource
                JOIN knowledge_resource_projections AS projection
                  ON projection.knowledge_resource_id =
                     resource.knowledge_resource_id
                 AND projection.active
                LEFT JOIN external_docs AS document
                  ON document.projection_revision_id =
                     projection.projection_revision_id
                 AND document.knowledge_resource_id =
                     resource.knowledge_resource_id
                WHERE resource.tenant_id = %s
                  AND resource.owner_scope_type = 'workspace'
                  AND resource.owner_scope_id = %s
                  AND resource.active
                  AND (
                      %s::text IS NULL
                      OR resource.owner_capability_code = %s
                  )
                  AND (
                      %s::text IS NULL
                      OR resource.source_app = %s
                  )
                  AND (
                      %s::text[] IS NULL
                      OR resource.source_id = ANY(%s::text[])
                  )
                GROUP BY
                    resource.knowledge_resource_id,
                    projection.projection_revision_id
                ORDER BY resource.updated_at DESC
                LIMIT %s
                """,
                (
                    access_context.tenant_id,
                    workspace_id,
                    owner_capability_code,
                    owner_capability_code,
                    source_app,
                    source_app,
                    list(source_ids) or None,
                    list(source_ids) or None,
                    bounded_limit,
                ),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            connection.commit()
            return rows
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def document_stats(
        self,
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
    ) -> dict[str, Any]:
        if not access_context.has_permission(
            "knowledge.read",
            scope_type="workspace",
            scope_id=workspace_id,
        ):
            raise PermissionError("legacy_document_read_permission_required")
        connection = self._connection_factory()
        try:
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            set_local_knowledge_context(cursor, access_context)
            cursor.execute(
                """
                WITH active_documents AS (
                    SELECT
                        resource.source_app,
                        resource.source_id,
                        resource.updated_at,
                        document.doc_type,
                        document.title,
                        document.last_synced_at
                    FROM knowledge_resources AS resource
                    JOIN knowledge_resource_projections AS projection
                      ON projection.knowledge_resource_id =
                         resource.knowledge_resource_id
                     AND projection.active
                    JOIN external_docs AS document
                      ON document.projection_revision_id =
                         projection.projection_revision_id
                     AND document.knowledge_resource_id =
                         resource.knowledge_resource_id
                    WHERE resource.tenant_id = %s
                      AND resource.owner_scope_type = 'workspace'
                      AND resource.owner_scope_id = %s
                      AND resource.active
                ),
                grouped AS (
                    SELECT
                        source_app,
                        doc_type,
                        COUNT(*)::integer AS count
                    FROM active_documents
                    GROUP BY source_app, doc_type
                ),
                recent AS (
                    SELECT DISTINCT ON (source_app, source_id)
                        source_app,
                        source_id,
                        title,
                        last_synced_at,
                        updated_at
                    FROM active_documents
                    ORDER BY
                        source_app,
                        source_id,
                        updated_at DESC
                )
                SELECT
                    (SELECT COUNT(*)::integer FROM active_documents)
                        AS total,
                    COALESCE(
                        (
                            SELECT JSONB_AGG(
                                TO_JSONB(grouped)
                                ORDER BY source_app, doc_type
                            )
                            FROM grouped
                        ),
                        '[]'::jsonb
                    ) AS by_source,
                    COALESCE(
                        (
                            SELECT JSONB_AGG(
                                TO_JSONB(recent_page)
                                ORDER BY updated_at DESC
                            )
                            FROM (
                                SELECT *
                                FROM recent
                                ORDER BY updated_at DESC
                                LIMIT 10
                            ) AS recent_page
                        ),
                        '[]'::jsonb
                    ) AS recent_syncs
                """,
                (access_context.tenant_id, workspace_id),
            )
            row = dict(cursor.fetchone() or {})
            connection.commit()
            return {
                "total": int(row.get("total") or 0),
                "by_source": list(row.get("by_source") or []),
                "recent_syncs": list(row.get("recent_syncs") or []),
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _require_project(
        access_context: RetrievalAccessContext,
        *,
        scope_type: str,
        scope_id: str,
    ) -> None:
        if not access_context.has_permission(
            "knowledge.project",
            scope_type=scope_type,
            scope_id=scope_id,
        ):
            raise PermissionError("legacy_document_project_permission_required")

    @staticmethod
    def _identity(
        *,
        access_context: RetrievalAccessContext,
        workspace_id: str,
        owner_capability_code: str,
        source_app: str,
        source_id: str,
        source_revision: str,
        owner_scope_type: str = "workspace",
        owner_scope_id: str | None = None,
    ) -> KnowledgeResourceIdentity:
        scope_id = owner_scope_id or workspace_id
        return KnowledgeResourceIdentity(
            tenant_id=access_context.tenant_id,
            owner_capability_code=owner_capability_code,
            source_kind="document",
            source_app=source_app,
            source_id=source_id,
            source_ref=f"document:{source_app}:{source_id}",
            source_revision=source_revision,
            owner_scope_type=owner_scope_type,
            owner_scope_id=scope_id,
            classification=(
                "group" if owner_scope_type == "group" else "workspace"
            ),
        )


__all__ = [
    "AuthorizedLegacyDocumentFacade",
    "LegacyDocumentChunk",
]
