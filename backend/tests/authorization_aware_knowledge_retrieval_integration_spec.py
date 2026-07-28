"""Disposable-PostgreSQL authorization and final-check matrix for retrieval."""

from __future__ import annotations

import os

import psycopg2
import pytest

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedKnowledgeIndexStore,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeAclMutation,
    KnowledgeGrant,
    KnowledgePermission,
    KnowledgeResourceIdentity,
    PrincipalRef,
    RetrievalAccessContext,
    ScopeMembership,
)
from backend.app.services.knowledge_projection.retrievable.document_adapter import (
    compile_document_projection,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    CitationLookup,
    KnowledgeRetrievalRequest,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)


TEST_VECTOR_URL = os.getenv("TEST_VECTOR_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_VECTOR_URL,
    reason="TEST_VECTOR_DATABASE_URL is required",
)


def _connection():
    return psycopg2.connect(TEST_VECTOR_URL)


class _VectorService:
    def _get_connection(self):
        return _connection()

    async def _generate_embedding_with_model(self, *_args, **_kwargs):
        return [1.0, 0.0], "bge-m3"


def _record(
    *,
    document_id: str,
    revision: str,
    checksum: str,
    content: str,
    embedding: list[float],
):
    return {
        "source_id": f"{document_id}:{revision}:chunk-1",
        "title": f"{document_id}.pdf",
        "content": content,
        "embedding": embedding,
        "metadata": {
            "workspace_id": "workspace-retrieval-spec",
            "document_id": document_id,
            "revision_id": revision,
            "checksum": checksum,
            "chunk_id": "chunk-1",
            "node_ids": ["node-1"],
            "source_locations": [{"page_or_slide": 1}],
            "heading_path": ["Retrieval"],
            "file_name": f"{document_id}.pdf",
            "active": True,
            "embedding_model": "bge-m3",
            "pipeline_version": "retrieval-spec.v1",
        },
    }


def _direct_context(user_id: str) -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
    )


def _owner_context(user_id: str) -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                "workspace-retrieval-spec",
            ),
            KnowledgePermission(
                "knowledge.manage_acl",
                "workspace",
                "workspace-retrieval-spec",
            ),
        ),
    )


def _member_context(user_id: str) -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
        memberships=(
            ScopeMembership(
                "workspace",
                "workspace-retrieval-spec",
                "member",
                "membership-revision-1",
            ),
        ),
    )


def _request(
    context: RetrievalAccessContext,
    *,
    modality_filter: str | None = None,
    query: str = "marker",
) -> KnowledgeRetrievalRequest:
    return KnowledgeRetrievalRequest(
        query=query,
        access_context=context,
        scope_type="workspace",
        scope_id="workspace-retrieval-spec",
        top_k=10,
        source_apps=("document_ingestion",),
        modality_filter=modality_filter,
    )


@pytest.mark.asyncio
async def test_acl_prefilter_excludes_higher_similarity_unauthorized_decoy() -> None:
    writer = AuthorizedKnowledgeIndexStore(_connection)
    authorized = writer.replace_trusted_document_revision(
        user_id="reader-user",
        workspace_id="workspace-retrieval-spec",
        document_id="authorized-doc",
        revision_id="rev-1",
        records=[
            _record(
                document_id="authorized-doc",
                revision="rev-1",
                checksum="d" * 64,
                content="AUTHORIZED_MARKER marker",
                embedding=[0.0, 1.0],
            )
        ],
    )
    writer.replace_trusted_document_revision(
        user_id="other-user",
        workspace_id="workspace-retrieval-spec",
        document_id="unauthorized-doc",
        revision_id="rev-1",
        records=[
            _record(
                document_id="unauthorized-doc",
                revision="rev-1",
                checksum="e" * 64,
                content="UNAUTHORIZED_DECOY marker",
                embedding=[1.0, 0.0],
            )
        ],
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )

    result = await facade.search(_request(_direct_context("reader-user")))

    assert result.transaction_count == 2
    assert [hit.knowledge_resource_id for hit in result.hits] == [
        authorized.knowledge_resource_id
    ]
    serialized = " ".join(hit.content for hit in result.hits)
    assert "AUTHORIZED_MARKER" in serialized
    assert "UNAUTHORIZED_DECOY" not in serialized


@pytest.mark.asyncio
async def test_cjk_prefix_keyword_recall_stays_inside_acl_prefilter() -> None:
    writer = AuthorizedKnowledgeIndexStore(_connection)
    authorized = writer.replace_trusted_document_revision(
        user_id="cjk-reader",
        workspace_id="workspace-retrieval-spec",
        document_id="cjk-authorized-doc",
        revision_id="rev-1",
        records=[
            _record(
                document_id="cjk-authorized-doc",
                revision="rev-1",
                checksum="1" * 64,
                content="瑜伽通常包含姿勢、呼吸技巧與放鬆成分。",
                embedding=[0.0, 1.0],
            )
        ],
    )
    writer.replace_trusted_document_revision(
        user_id="other-cjk-reader",
        workspace_id="workspace-retrieval-spec",
        document_id="cjk-unauthorized-doc",
        revision_id="rev-1",
        records=[
            _record(
                document_id="cjk-unauthorized-doc",
                revision="rev-1",
                checksum="2" * 64,
                content="瑜伽包含呼吸練習，但這筆資料未授權。",
                embedding=[1.0, 0.0],
            )
        ],
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )

    result = await facade.search(
        _request(
            _direct_context("cjk-reader"),
            query="瑜伽包含呼吸練習嗎？",
        )
    )

    assert "keyword_empty" not in result.degraded_reasons
    assert [hit.knowledge_resource_id for hit in result.hits] == [
        authorized.knowledge_resource_id
    ]
    assert result.hits[0].channels == ("text_vector", "keyword")


@pytest.mark.asyncio
async def test_hybrid_modality_filter_only_admits_active_matching_channels() -> None:
    writer = AuthorizedKnowledgeIndexStore(_connection)
    written = writer.replace_trusted_document_revision(
        user_id="modality-reader",
        workspace_id="workspace-retrieval-spec",
        document_id="modality-doc",
        revision_id="rev-1",
        records=[
            _record(
                document_id="modality-doc",
                revision="rev-1",
                checksum="8" * 64,
                content="MODALITY_MARKER marker",
                embedding=[1.0, 0.0],
            )
        ],
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    context = _direct_context("modality-reader")

    text_result = await facade.search(
        _request(context, modality_filter="text")
    )
    image_result = await facade.search(
        _request(context, modality_filter="image")
    )

    assert written.knowledge_resource_id in {
        hit.knowledge_resource_id for hit in text_result.hits
    }
    assert image_result.hits == ()


@pytest.mark.asyncio
async def test_hybrid_query_evidence_ref_is_hydrated_and_final_checked() -> None:
    writer = AuthorizedKnowledgeIndexStore(_connection)
    records = [
        _record(
            document_id="query-seed-doc",
            revision="rev-1",
            checksum="7" * 64,
            content="QUERY_SEED_MARKER marker",
            embedding=[1.0, 0.0],
        )
    ]
    writer.replace_trusted_document_revision(
        user_id="query-seed-reader",
        workspace_id="workspace-retrieval-spec",
        document_id="query-seed-doc",
        revision_id="rev-1",
        records=records,
    )
    payload, documents = compile_document_projection(
        workspace_id="workspace-retrieval-spec",
        document_id="query-seed-doc",
        revision_id="rev-1",
        records=records,
    )
    writer.replace_projection(
        access_context=_owner_context("query-seed-reader"),
        identity=KnowledgeResourceIdentity(
            tenant_id="local",
            owner_capability_code="document_ingestion",
            source_kind="document",
            source_app="document_ingestion",
            source_id="query-seed-doc",
            source_ref="document:query-seed-doc",
            source_revision="rev-1",
            owner_scope_type="workspace",
            owner_scope_id="workspace-retrieval-spec",
        ),
        payload=payload,
        documents=documents,
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    context = _direct_context("query-seed-reader")
    initial = await facade.search(_request(context))
    citation = next(
        hit.citation
        for hit in initial.hits
        if "QUERY_SEED_MARKER" in hit.content
    )

    seeded = await facade.search(
        KnowledgeRetrievalRequest(
            query="",
            query_evidence_refs=(
                CitationLookup(
                    citation_id=str(citation["citation_id"]),
                    content_hash=str(citation["content_hash"]),
                ),
            ),
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-retrieval-spec",
            top_k=10,
            source_apps=("document_ingestion",),
        )
    )

    assert seeded.transaction_count == 2
    assert "query_evidence_vector_channel_not_admitted" in (
        seeded.degraded_reasons
    )
    assert any(
        "QUERY_SEED_MARKER" in hit.content for hit in seeded.hits
    )


@pytest.mark.asyncio
async def test_role_allow_and_direct_user_deny_have_deny_precedence() -> None:
    writer = AuthorizedKnowledgeIndexStore(_connection)
    records = [
        _record(
            document_id="role-doc",
            revision="rev-1",
            checksum="f" * 64,
            content="ROLE_VISIBLE marker",
            embedding=[0.5, 0.5],
        )
    ]
    first = writer.replace_trusted_document_revision(
        user_id="role-owner",
        workspace_id="workspace-retrieval-spec",
        document_id="role-doc",
        revision_id="rev-1",
        records=records,
    )
    payload, documents = compile_document_projection(
        workspace_id="workspace-retrieval-spec",
        document_id="role-doc",
        revision_id="rev-1",
        records=records,
    )
    identity = KnowledgeResourceIdentity(
        tenant_id="local",
        owner_capability_code="document_ingestion",
        source_kind="document",
        source_app="document_ingestion",
        source_id="role-doc",
        source_ref="document:role-doc",
        source_revision="rev-1",
        owner_scope_type="workspace",
        owner_scope_id="workspace-retrieval-spec",
    )
    allowed = writer.replace_projection(
        access_context=_owner_context("role-owner"),
        identity=identity,
        payload=payload,
        documents=documents,
        acl_mutation=KnowledgeAclMutation(
            expected_authz_revision=1,
            grants=(
                KnowledgeGrant(
                    PrincipalRef("user", "role-owner"),
                    relation="owner",
                ),
                KnowledgeGrant(
                    PrincipalRef(
                        "workspace_role",
                        "workspace-retrieval-spec:member",
                    ),
                    relation="reader",
                ),
            ),
        ),
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    member = _member_context("role-member")

    allowed_result = await facade.search(_request(member))

    assert first.knowledge_resource_id in {
        hit.knowledge_resource_id for hit in allowed_result.hits
    }
    writer.replace_projection(
        access_context=_owner_context("role-owner"),
        identity=identity,
        payload=payload,
        documents=documents,
        acl_mutation=KnowledgeAclMutation(
            expected_authz_revision=allowed.authz_revision,
            grants=(
                KnowledgeGrant(
                    PrincipalRef("user", "role-owner"),
                    relation="owner",
                ),
                KnowledgeGrant(
                    PrincipalRef(
                        "workspace_role",
                        "workspace-retrieval-spec:member",
                    ),
                    relation="reader",
                ),
                KnowledgeGrant(
                    PrincipalRef("user", "role-member"),
                    relation="reader",
                    effect="deny",
                ),
            ),
        ),
    )

    denied_result = await facade.search(_request(member))

    assert first.knowledge_resource_id not in {
        hit.knowledge_resource_id for hit in denied_result.hits
    }


class _RevokingFinalCheckStore:
    def __init__(self):
        self._delegate = AuthorizationAwareKnowledgeRetrievalStore(_connection)
        self._revoked = False

    def fetch_hybrid_candidates(self, **kwargs):
        return self._delegate.fetch_hybrid_candidates(**kwargs)

    def final_authorize(self, **kwargs):
        if not self._revoked:
            expected = list(kwargs["expected_bindings"])
            kwargs["expected_bindings"] = expected
            if expected:
                resource_id = expected[0][0]
                connection = _connection()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE knowledge_security_labels AS label
                            SET authz_revision = authz_revision + 1,
                                updated_at = NOW()
                            FROM knowledge_resources AS resource
                            WHERE resource.knowledge_resource_id = %s
                              AND resource.security_label_id =
                                  label.security_label_id
                            """,
                            (resource_id,),
                        )
                    connection.commit()
                finally:
                    connection.close()
                self._revoked = True
        return self._delegate.final_authorize(**kwargs)


@pytest.mark.asyncio
async def test_final_batch_check_drops_candidate_revoked_after_ranking() -> None:
    writer = AuthorizedKnowledgeIndexStore(_connection)
    result = writer.replace_trusted_document_revision(
        user_id="race-user",
        workspace_id="workspace-retrieval-spec",
        document_id="race-doc",
        revision_id="rev-1",
        records=[
            _record(
                document_id="race-doc",
                revision="rev-1",
                checksum="9" * 64,
                content="RACE_MARKER marker",
                embedding=[1.0, 0.0],
            )
        ],
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
        store=_RevokingFinalCheckStore(),
    )

    response = await facade.search(_request(_direct_context("race-user")))

    assert result.knowledge_resource_id not in {
        hit.knowledge_resource_id for hit in response.hits
    }
    assert response.transaction_count == 2
