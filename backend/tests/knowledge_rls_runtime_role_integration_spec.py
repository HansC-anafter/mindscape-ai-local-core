"""Disposable-DB proof for the non-owner knowledge RLS runtime."""

from __future__ import annotations

import os

import psycopg2
import pytest

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedKnowledgeIndexStore,
)
from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
    set_local_knowledge_context,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    KnowledgeRetrievalRequest,
)
from backend.app.services.knowledge_projection.legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)


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
