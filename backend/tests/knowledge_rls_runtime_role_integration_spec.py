"""Disposable-DB proof for the non-owner knowledge RLS runtime."""

from __future__ import annotations

import hashlib
import os

import psycopg2
import pytest

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedKnowledgeIndexStore,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeGrant,
    KnowledgePermission,
    KnowledgeResourceIdentity,
    PrincipalRef,
    RetrievalAccessContext,
    set_local_knowledge_context,
    visibility_partition_hash_for_grants,
)
from backend.app.services.knowledge_graph.contracts import (
    GraphEntityWrite,
    GraphMentionWrite,
    GraphProjectionWrite,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ProjectionChannelWrite,
    ProjectionEvidenceWrite,
    ProjectionRecordWrite,
    RetrievableProjectionWrite,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    KnowledgeRetrievalRequest,
)
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)
from backend.app.services.tool_embedding_service import ToolEmbeddingService


TEST_VECTOR_URL = os.getenv("TEST_VECTOR_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_VECTOR_URL,
    reason="TEST_VECTOR_DATABASE_URL is required",
)
RUNTIME_ROLE = "mindscape_vector_runtime"
WORKSPACE_ID = "workspace-knowledge-rls-runtime-spec"
OWNER_ID = "knowledge-rls-owner"


def _owner_connection():
    return psycopg2.connect(TEST_VECTOR_URL)


def _runtime_connection():
    connection = psycopg2.connect(TEST_VECTOR_URL)
    cursor = connection.cursor()
    cursor.execute(f"SET ROLE {RUNTIME_ROLE}")
    return connection


def _context(user_id: str) -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
        permissions=(
            KnowledgePermission(
                "knowledge.read",
                "workspace",
                WORKSPACE_ID,
            ),
        ),
    )


def _project_context(user_id: str) -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
        permissions=(
            KnowledgePermission(
                "knowledge.read",
                "workspace",
                WORKSPACE_ID,
            ),
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                WORKSPACE_ID,
            ),
        ),
    )


def _record():
    return {
        "source_id": "rls-document:revision-1:chunk-1",
        "title": "rls.txt",
        "content": "KNOWLEDGE_RLS_RUNTIME_MARKER",
        "embedding": [1.0, 0.0],
        "metadata": {
            "workspace_id": WORKSPACE_ID,
            "document_id": "rls-document",
            "revision_id": "revision-1",
            "checksum": "e" * 64,
            "chunk_id": "chunk-1",
            "node_ids": [],
            "source_locations": [],
            "active": True,
            "embedding_model": "bge-m3",
            "pipeline_version": "knowledge-rls-runtime-spec.v1",
        },
    }


def _graph_payload(source_id: str) -> RetrievableProjectionWrite:
    marker = f"KNOWLEDGE_RLS_GRAPH_{source_id}"
    content_hash = hashlib.sha256(marker.encode("utf-8")).hexdigest()
    visibility_hash = visibility_partition_hash_for_grants(
        (
            KnowledgeGrant(
                PrincipalRef("user", OWNER_ID),
                relation="owner",
            ),
        )
    )
    graph = GraphProjectionWrite(
        algorithm_revision="runtime-role-spec.v1",
        resolver_revision="runtime-role-spec.v1",
        visibility_partition_hash=visibility_hash,
        entities=(
            GraphEntityWrite(
                "shared-runtime-role-entity",
                "concept",
                "runtime-role-spec.v1",
            ),
        ),
        mentions=(
            GraphMentionWrite(
                entity_key="shared-runtime-role-entity",
                evidence_unit_key="unit-1",
                record_key="record-1",
                surface_text=marker,
                mention_type="concept",
                confidence=1.0,
                citation={
                    "source_ref": f"object:{source_id}",
                    "anchor": "unit-1",
                },
                extractor_revision="runtime-role-spec.v1",
                model_revision="runtime-role-spec.v1",
                prompt_revision="runtime-role-spec.v1",
            ),
        ),
        relations=(),
    )
    return RetrievableProjectionWrite(
        source_instance_id=source_id,
        source_revision="revision-1",
        content_hash=content_hash,
        descriptor_id="runtime_role_graph_spec",
        descriptor_revision="runtime-role-spec.v1",
        projector_revision="runtime-role-spec.v1",
        facet_schema_revision="runtime-role-spec.v1",
        embedding_profile_revision="runtime-role-spec.v1",
        projection_hash=hashlib.sha256(
            f"{source_id}:{content_hash}".encode("utf-8")
        ).hexdigest(),
        evidence_units=(
            ProjectionEvidenceWrite(
                unit_key="unit-1",
                unit_kind="text_span",
                owner_asset_ref=f"object:{source_id}",
                content_hash=content_hash,
                media_type="text/plain",
                anchor={"kind": "text_span", "start": 0, "end": len(marker)},
            ),
        ),
        channels=(
            ProjectionChannelWrite(
                unit_key="unit-1",
                channel_id="text.not-admitted",
                modality="text",
                profile_revision="runtime-role-spec.v1",
                model_revision=None,
                dimension=None,
                calibration_revision=None,
                index_revision=None,
                required=False,
                state="not_admitted",
                row_count=0,
                byte_count=0,
                reason="runtime_role_graph_spec_no_vector",
            ),
        ),
        records=(
            ProjectionRecordWrite(
                record_kind="concept",
                record_key="record-1",
                search_text=marker,
                citation={
                    "source_ref": f"object:{source_id}",
                    "anchor": "unit-1",
                },
                values={"marker": marker},
                content_hash=content_hash,
            ),
        ),
        relation_count=0,
        graph_complete=True,
        graph_required=True,
        graph=graph,
    )


class _VectorService:
    def _get_connection(self):
        return _runtime_connection()

    async def _generate_embedding_with_model(self, *_args, **_kwargs):
        return [1.0, 0.0], "bge-m3"


@pytest.mark.asyncio
async def test_runtime_role_rls_and_transaction_reset() -> None:
    owner = _owner_connection()
    try:
        cursor = owner.cursor()
        cursor.execute(
            """
            SELECT
                role.rolsuper,
                role.rolbypassrls,
                role.rolinherit,
                table_row.relrowsecurity,
                table_row.relforcerowsecurity,
                pg_get_userbyid(table_row.relowner)
            FROM pg_roles AS role
            CROSS JOIN pg_class AS table_row
            WHERE role.rolname = %s
              AND table_row.oid = 'public.external_docs'::regclass
            """,
            (RUNTIME_ROLE,),
        )
        row = cursor.fetchone()
        assert row == (False, False, False, True, True, "mindscape")
    finally:
        owner.close()

    written = AuthorizedKnowledgeIndexStore(
        _runtime_connection
    ).replace_trusted_document_revision(
        user_id=OWNER_ID,
        workspace_id=WORKSPACE_ID,
        document_id="rls-document",
        revision_id="revision-1",
        records=[_record()],
    )
    assert written.state in {"indexed", "reused"}

    result = await AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService()
    ).search(
        KnowledgeRetrievalRequest(
            query="KNOWLEDGE_RLS_RUNTIME_MARKER",
            access_context=_context(OWNER_ID),
            scope_type="workspace",
            scope_id=WORKSPACE_ID,
            top_k=5,
        )
    )
    assert [item.content for item in result.hits] == [
        "KNOWLEDGE_RLS_RUNTIME_MARKER"
    ]

    connection = _runtime_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM external_docs")
        assert cursor.fetchone()[0] == 0
        set_local_knowledge_context(cursor, _context(OWNER_ID))
        cursor.execute("SELECT COUNT(*) FROM external_docs")
        assert cursor.fetchone()[0] == 1
        connection.commit()
        cursor.execute("SELECT COUNT(*) FROM external_docs")
        assert cursor.fetchone()[0] == 0
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute(
                "CREATE TABLE forbidden_runtime_ddl (id integer)"
            )
        connection.rollback()
        set_local_knowledge_context(
            cursor,
            _project_context(OWNER_ID),
            write_scope_type="workspace",
            write_scope_id=WORKSPACE_ID,
            write_resource_id="kr_expected",
            write_security_label_id="ksl_expected",
        )
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO knowledge_security_labels (
                    security_label_id,
                    classification,
                    authz_revision
                ) VALUES ('ksl_cross_label', 'workspace', 1)
                """
            )
        connection.rollback()
    finally:
        connection.close()

    denied = await AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService()
    ).search(
        KnowledgeRetrievalRequest(
            query="KNOWLEDGE_RLS_RUNTIME_MARKER",
            access_context=_context("other-user"),
            scope_type="workspace",
            scope_id=WORKSPACE_ID,
            top_k=5,
        )
    )
    assert denied.hits == ()


def test_runtime_role_graph_entity_upsert_is_scoped_and_idempotent() -> None:
    store = AuthorizedKnowledgeIndexStore(_runtime_connection)
    for source_id in ("runtime-graph-source-a", "runtime-graph-source-b"):
        written = store.replace_projection(
            access_context=_project_context(OWNER_ID),
            identity=KnowledgeResourceIdentity(
                tenant_id="local",
                owner_capability_code="runtime_role_graph_spec",
                source_kind="object",
                source_app="runtime_role_graph_spec",
                source_id=source_id,
                source_ref=f"object:{source_id}",
                source_revision="revision-1",
                owner_scope_type="workspace",
                owner_scope_id=WORKSPACE_ID,
                classification="workspace",
            ),
            payload=_graph_payload(source_id),
            documents=(),
        )
        assert written.state == "indexed"

    connection = _runtime_connection()
    try:
        cursor = connection.cursor()
        set_local_knowledge_context(cursor, _context(OWNER_ID))
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT entity.entity_id),
                COUNT(mention.mention_id)
            FROM knowledge_graph_entities AS entity
            JOIN knowledge_graph_mentions AS mention
              ON mention.entity_id = entity.entity_id
            WHERE entity.scope_type = 'workspace'
              AND entity.scope_id = %s
              AND entity.canonical_key = 'shared-runtime-role-entity'
            """,
            (WORKSPACE_ID,),
        )
        assert cursor.fetchone() == (1, 2)
        connection.commit()
    finally:
        connection.close()

    other_workspace_id = "workspace-knowledge-rls-runtime-other"
    other_context = RetrievalAccessContext.create(
        subject_user_id=OWNER_ID,
        tenant_id="local",
        principals=(PrincipalRef("user", OWNER_ID),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                other_workspace_id,
            ),
        ),
    )
    connection = _runtime_connection()
    try:
        cursor = connection.cursor()
        set_local_knowledge_context(
            cursor,
            other_context,
            write_scope_type="workspace",
            write_scope_id=other_workspace_id,
            write_resource_id="kr_runtime_graph_other",
            write_security_label_id="ksl_runtime_graph_other",
        )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM knowledge_graph_entities
            WHERE scope_type = 'workspace'
              AND scope_id = %s
              AND canonical_key = 'shared-runtime-role-entity'
            """,
            (WORKSPACE_ID,),
        )
        assert cursor.fetchone() == (0,)
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cursor.execute(
                """
                INSERT INTO knowledge_graph_entities (
                    entity_id, tenant_id, scope_type, scope_id,
                    canonical_key, entity_type, resolver_revision
                ) VALUES (
                    'kge_cross_scope_forbidden', 'local', 'workspace', %s,
                    'cross-scope-forbidden', 'concept', 'runtime-role-spec.v1'
                )
                """,
                (WORKSPACE_ID,),
            )
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_runtime_role_verifies_and_writes_migration_owned_tool_embeddings():
    service = ToolEmbeddingService()
    service._get_connection = _runtime_connection

    await service.ensure_table()
    connection = _runtime_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO tool_embeddings (
                tool_id,
                display_name,
                description,
                category,
                capability_code,
                embedding_model,
                embedding_dim
            ) VALUES (
                'knowledge-runtime-migration-probe',
                'Knowledge migration probe',
                'Rollback-only runtime DML proof',
                'data',
                'local_core',
                'none',
                0
            )
            ON CONFLICT (tool_id, embedding_model)
            DO UPDATE SET updated_at = NOW()
            RETURNING tool_id
            """
        )
        assert cursor.fetchone() == (
            "knowledge-runtime-migration-probe",
        )
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_legacy_document_paths_delegate_to_authorized_writer() -> None:
    facade = AuthorizedLegacyDocumentFacade(
        vector_service=_VectorService()
    )
    context = _project_context(OWNER_ID)
    written = await facade.replace_document(
        access_context=context,
        workspace_id=WORKSPACE_ID,
        owner_capability_code="external_docs",
        source_app="legacy-spec",
        source_id="legacy-document-1",
        doc_type="external_document",
        chunks=(
            LegacyDocumentChunk(
                content="LEGACY_AUTHORIZED_FACADE_MARKER",
                title="legacy.txt",
                metadata={"kind": "compatibility"},
            ),
        ),
    )
    assert written.knowledge_resource_id
    rows = facade.list_documents(
        access_context=context,
        workspace_id=WORKSPACE_ID,
        owner_capability_code="external_docs",
        source_app="legacy-spec",
        limit=10,
    )
    assert [(row["source_id"], row["chunk_count"]) for row in rows] == [
        ("legacy-document-1", 1)
    ]
    stats = facade.document_stats(
        access_context=context,
        workspace_id=WORKSPACE_ID,
    )
    assert stats["total"] >= 2
    revoked = facade.revoke_document(
        access_context=context,
        workspace_id=WORKSPACE_ID,
        owner_capability_code="external_docs",
        source_app="legacy-spec",
        source_id="legacy-document-1",
    )
    assert revoked is not None
    assert facade.active_revision(
        access_context=context,
        workspace_id=WORKSPACE_ID,
        owner_capability_code="external_docs",
        source_app="legacy-spec",
        source_id="legacy-document-1",
    ) is None
