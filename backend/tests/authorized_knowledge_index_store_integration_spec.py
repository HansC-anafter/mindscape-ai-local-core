"""Disposable-PostgreSQL acceptance for the single authorized vector writer."""

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
)
from backend.app.services.knowledge_projection.retrievable.document_adapter import (
    compile_document_projection,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ProjectionChannelWrite,
    ProjectionEvidenceWrite,
    ProjectionFacetWrite,
    ProjectionRecordWrite,
    RetrievableProjectionWrite,
)


TEST_VECTOR_URL = os.getenv("TEST_VECTOR_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_VECTOR_URL,
    reason="TEST_VECTOR_DATABASE_URL is required",
)


def _connection():
    return psycopg2.connect(TEST_VECTOR_URL)


def _records(
    *,
    revision: str,
    checksum: str,
    suffix: str = "",
    workspace_id: str = "workspace-writer-spec",
    document_id: str = "writer-doc",
):
    result = []
    for index, content in enumerate(("alpha evidence", "beta evidence"), start=1):
        chunk_id = f"chunk-{index}{suffix}"
        result.append(
            {
                "source_id": f"{document_id}:{revision}:{chunk_id}",
                "title": "writer-spec.pdf",
                "content": content + suffix,
                "embedding": [0.1 * index, 0.2 * index],
                "metadata": {
                    "workspace_id": workspace_id,
                    "document_id": document_id,
                    "revision_id": revision,
                    "checksum": checksum,
                    "chunk_id": chunk_id,
                    "active": True,
                    "embedding_model": "bge-m3",
                    "pipeline_version": "writer-spec.v1",
                    "media_type": "application/pdf",
                },
            }
        )
    return result


def _query_one(statement: str, params=()):
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement, params)
            return cursor.fetchone()
    finally:
        connection.close()


def test_writer_binds_every_row_and_preserves_acl_across_reindex() -> None:
    store = AuthorizedKnowledgeIndexStore(_connection)
    first_records = _records(revision="rev-1", checksum="a" * 64)

    first = store.replace_trusted_document_revision(
        user_id="writer-user",
        workspace_id="workspace-writer-spec",
        document_id="writer-doc",
        revision_id="rev-1",
        records=first_records,
    )
    reused = store.replace_trusted_document_revision(
        user_id="writer-user",
        workspace_id="workspace-writer-spec",
        document_id="writer-doc",
        revision_id="rev-1",
        records=first_records,
    )

    assert first.state == "indexed"
    assert reused.state == "reused"
    assert reused.projection_revision_id == first.projection_revision_id
    assert _query_one(
        """
        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE knowledge_resource_id = %s
                  AND security_label_id = %s
                  AND projection_revision_id = %s
            )
        FROM external_docs
        WHERE knowledge_resource_id = %s
        """,
        (
            first.knowledge_resource_id,
            first.security_label_id,
            first.projection_revision_id,
            first.knowledge_resource_id,
        ),
    ) == (2, 2)
    assert _query_one(
        """
        SELECT
            (SELECT COUNT(*) FROM knowledge_evidence_units
             WHERE projection_revision_id = %s),
            (SELECT COUNT(*) FROM knowledge_embedding_channel_receipts
             WHERE projection_revision_id = %s AND state = 'active'),
            (SELECT COUNT(*) FROM knowledge_security_label_grants
             WHERE security_label_id = %s AND authz_revision = 1),
            (SELECT COUNT(*) FROM knowledge_acl_audit_log
             WHERE knowledge_resource_id = %s)
        """,
        (
            first.projection_revision_id,
            first.projection_revision_id,
            first.security_label_id,
            first.knowledge_resource_id,
        ),
    ) == (2, 2, 1, 1)

    payload, documents = compile_document_projection(
        workspace_id="workspace-writer-spec",
        document_id="writer-doc",
        revision_id="rev-1",
        records=first_records,
    )
    access_context = RetrievalAccessContext.create(
        subject_user_id="writer-user",
        tenant_id="local",
        principals=(PrincipalRef("user", "writer-user"),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                "workspace-writer-spec",
            ),
            KnowledgePermission(
                "knowledge.manage_acl",
                "workspace",
                "workspace-writer-spec",
            ),
        ),
    )
    identity = KnowledgeResourceIdentity(
        tenant_id="local",
        owner_capability_code="document_ingestion",
        source_kind="document",
        source_app="document_ingestion",
        source_id="writer-doc",
        source_ref="document:writer-doc",
        source_revision="rev-1",
        owner_scope_type="workspace",
        owner_scope_id="workspace-writer-spec",
    )
    acl_result = store.replace_projection(
        access_context=access_context,
        identity=identity,
        payload=payload,
        documents=documents,
        acl_mutation=KnowledgeAclMutation(
            expected_authz_revision=1,
            grants=(
                KnowledgeGrant(
                    PrincipalRef("user", "writer-user"),
                    relation="owner",
                ),
                KnowledgeGrant(
                    PrincipalRef(
                        "workspace_role",
                        "workspace-writer-spec:member",
                    ),
                    relation="reader",
                ),
            ),
        ),
    )
    assert acl_result.authz_revision == 2

    second = store.replace_trusted_document_revision(
        user_id="writer-user",
        workspace_id="workspace-writer-spec",
        document_id="writer-doc",
        revision_id="rev-2",
        records=_records(
            revision="rev-2",
            checksum="b" * 64,
            suffix="-v2",
        ),
    )
    assert second.authz_revision == 2
    assert second.security_label_id == first.security_label_id
    assert second.projection_revision_id != first.projection_revision_id
    assert _query_one(
        """
        SELECT
            label.authz_revision,
            COUNT(grant_row.*),
            COUNT(*) FILTER (
                WHERE grant_row.principal_type = 'workspace_role'
            )
        FROM knowledge_security_labels AS label
        JOIN knowledge_security_label_grants AS grant_row
          ON grant_row.security_label_id = label.security_label_id
         AND grant_row.authz_revision = label.authz_revision
        WHERE label.security_label_id = %s
        GROUP BY label.authz_revision
        """,
        (first.security_label_id,),
    ) == (2, 2, 1)
    assert _query_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE active),
            COUNT(*) FILTER (WHERE status = 'superseded')
        FROM knowledge_resource_projections
        WHERE knowledge_resource_id = %s
        """,
        (first.knowledge_resource_id,),
        ) == (1, 2)


def test_writer_failpoint_rolls_back_complete_new_generation() -> None:
    baseline = _query_one(
        """
        SELECT projection_revision_id, COUNT(*)
        FROM external_docs
        WHERE metadata->>'document_id' = 'writer-doc'
        GROUP BY projection_revision_id
        """
    )

    def fail_after_channel_write(step: str) -> None:
        if step == "new_chunks_inserted":
            raise RuntimeError("injected_after_channel_write")

    store = AuthorizedKnowledgeIndexStore(
        _connection,
        failpoint=fail_after_channel_write,
    )
    with pytest.raises(RuntimeError, match="injected_after_channel_write"):
        store.replace_trusted_document_revision(
            user_id="writer-user",
            workspace_id="workspace-writer-spec",
            document_id="writer-doc",
            revision_id="rev-3",
            records=_records(
                revision="rev-3",
                checksum="c" * 64,
                suffix="-v3",
            ),
        )

    assert _query_one(
        """
        SELECT projection_revision_id, COUNT(*)
        FROM external_docs
        WHERE metadata->>'document_id' = 'writer-doc'
        GROUP BY projection_revision_id
        """
    ) == baseline
    assert _query_one(
        """
        SELECT COUNT(*)
        FROM knowledge_resource_projections
        WHERE source_instance_id = 'writer-doc'
          AND source_revision = 'rev-3'
        """
    ) == (0,)


def test_legacy_rows_have_exact_stable_acl_bindings() -> None:
    if os.getenv("TEST_VECTOR_EXPECT_LEGACY_BASELINE") != "1":
        pytest.skip(
            "legacy baseline assertions require an explicitly seeded database"
        )
    assert _query_one(
        """
        SELECT
            COUNT(*),
            COUNT(*) FILTER (
                WHERE knowledge_resource_id IS NULL
                   OR security_label_id IS NULL
            ),
            COUNT(DISTINCT knowledge_resource_id),
            COUNT(DISTINCT security_label_id)
        FROM external_docs
        WHERE metadata->>'workspace_id' =
              'bac7ce63-e768-454d-96f3-3a00e8e1df69'
        """
    ) == (7, 0, 3, 3)


def test_revoke_is_revision_checked_non_destructive_and_idempotent() -> None:
    store = AuthorizedKnowledgeIndexStore(_connection)
    workspace_id = "workspace-revoke-spec"
    document_id = "revoke-doc-20260727"
    revision_id = "revoke-revision-1"
    payload, documents = compile_document_projection(
        workspace_id=workspace_id,
        document_id=document_id,
        revision_id=revision_id,
        records=_records(
            revision=revision_id,
            checksum="d" * 64,
            suffix="-revoke",
            workspace_id=workspace_id,
            document_id=document_id,
        ),
    )
    context = RetrievalAccessContext.create(
        subject_user_id="revoke-user",
        tenant_id="local",
        principals=(PrincipalRef("user", "revoke-user"),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                workspace_id,
            ),
        ),
    )
    identity = KnowledgeResourceIdentity(
        tenant_id="local",
        owner_capability_code="revoke_spec",
        source_kind="document",
        source_app="revoke_spec",
        source_id=document_id,
        source_ref=f"document:{document_id}",
        source_revision=revision_id,
        owner_scope_type="workspace",
        owner_scope_id=workspace_id,
    )
    projected = store.replace_projection(
        access_context=context,
        identity=identity,
        payload=payload,
        documents=documents,
    )

    revoked = store.revoke_projection(
        access_context=context,
        identity=identity,
    )
    reused = store.revoke_projection(
        access_context=context,
        identity=identity,
    )

    assert revoked.state == "revoked"
    assert reused.state == "reused"
    assert revoked.knowledge_resource_id == projected.knowledge_resource_id
    assert _query_one(
        """
        SELECT
            resource.active,
            projection.active,
            projection.status,
            COUNT(DISTINCT document.id),
            COUNT(DISTINCT document.id) FILTER (
                WHERE document.metadata->>'active' = 'false'
                  AND document.metadata->>'revoked' = 'true'
            ),
            COUNT(DISTINCT channel.channel_receipt_id)
                FILTER (WHERE channel.state = 'revoked')
        FROM knowledge_resources AS resource
        JOIN knowledge_resource_projections AS projection
          ON projection.knowledge_resource_id =
             resource.knowledge_resource_id
        LEFT JOIN external_docs AS document
          ON document.projection_revision_id =
             projection.projection_revision_id
        LEFT JOIN knowledge_embedding_channel_receipts AS channel
          ON channel.projection_revision_id =
             projection.projection_revision_id
        WHERE resource.knowledge_resource_id = %s
        GROUP BY resource.active, projection.active, projection.status
        """,
        (projected.knowledge_resource_id,),
    ) == (False, False, "revoked", 2, 2, 2)
    restored = store.replace_projection(
        access_context=context,
        identity=identity,
        payload=payload,
        documents=documents,
    )
    assert restored.state == "indexed"
    assert restored.projection_revision_id == projected.projection_revision_id
    assert _query_one(
        """
        SELECT
            resource.active,
            projection.active,
            projection.status,
            COUNT(DISTINCT channel.channel_receipt_id)
                FILTER (WHERE channel.state = 'active'),
            COUNT(DISTINCT document.id)
                FILTER (WHERE document.metadata->>'active' = 'true')
        FROM knowledge_resources AS resource
        JOIN knowledge_resource_projections AS projection
          ON projection.knowledge_resource_id =
             resource.knowledge_resource_id
        LEFT JOIN knowledge_embedding_channel_receipts AS channel
          ON channel.projection_revision_id =
             projection.projection_revision_id
        LEFT JOIN external_docs AS document
          ON document.projection_revision_id =
             projection.projection_revision_id
        WHERE resource.knowledge_resource_id = %s
        GROUP BY resource.active, projection.active, projection.status
        """,
        (projected.knowledge_resource_id,),
    ) == (True, True, "active", 2, 2)
    stale_identity = KnowledgeResourceIdentity(
        **{
            **identity.__dict__,
            "source_revision": "stale-revision",
        }
    )
    with pytest.raises(
        RuntimeError,
        match="knowledge_projection_revoke_source_revision_conflict",
    ):
        store.revoke_projection(
            access_context=context,
            identity=stale_identity,
        )


def test_two_pack_neutral_pointer_only_modalities_use_additive_channel_receipts() -> None:
    store = AuthorizedKnowledgeIndexStore(_connection)
    context = RetrievalAccessContext.create(
        subject_user_id="multimodal-user",
        tenant_id="local",
        principals=(PrincipalRef("user", "multimodal-user"),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "group",
                "group-multimodal-spec",
            ),
        ),
    )
    results = []
    for index, capability_code in enumerate(
        ("synthetic_alpha", "synthetic_beta"),
        start=1,
    ):
        source_id = f"multimodal-source-{index}"
        payload = RetrievableProjectionWrite(
            source_instance_id=source_id,
            source_revision="revision-1",
            content_hash=f"{index}" * 64,
            descriptor_id="portable_asset",
            descriptor_revision="descriptor.v1",
            projector_revision="projector.v1",
            facet_schema_revision="facets.v1",
            embedding_profile_revision="image.pointer-only.v1",
            projection_hash=f"{index + 2}" * 64,
            evidence_units=(
                ProjectionEvidenceWrite(
                    unit_key="hero-image",
                    unit_kind="image_region",
                    owner_asset_ref=f"object:{source_id}",
                    content_hash=f"{index + 4}" * 64,
                    media_type="image/png",
                    anchor={
                        "kind": "image_region",
                        "x": 0.0,
                        "y": 0.0,
                        "width": 1.0,
                        "height": 1.0,
                    },
                ),
            ),
            channels=(
                ProjectionChannelWrite(
                    unit_key="hero-image",
                    channel_id="image.pointer",
                    modality="image",
                    profile_revision="image.pointer-only.v1",
                    model_revision=None,
                    dimension=None,
                    calibration_revision=None,
                    index_revision=None,
                    required=True,
                    state="not_admitted",
                    row_count=0,
                    byte_count=0,
                    reason="native_image_channel_not_installed",
                ),
            ),
            records=(
                ProjectionRecordWrite(
                    record_kind="asset",
                    record_key="hero-image",
                    search_text="portable image asset",
                    citation={"source_ref": f"object:{source_id}"},
                    values={"asset_kind": "hero"},
                    content_hash=f"{index + 6}" * 64,
                    facets=(
                        ProjectionFacetWrite(
                            key="asset_kind",
                            value_type="string",
                            value="hero",
                        ),
                    ),
                ),
            ),
        )
        result = store.replace_projection(
            access_context=context,
            identity=KnowledgeResourceIdentity(
                tenant_id="local",
                owner_capability_code=capability_code,
                source_kind="object",
                source_app=capability_code,
                source_id=source_id,
                source_ref=f"object:{source_id}",
                source_revision="revision-1",
                owner_scope_type="group",
                owner_scope_id="group-multimodal-spec",
                classification="group",
            ),
            payload=payload,
            documents=(),
        )
        results.append(result)

    assert {result.state for result in results} == {"degraded"}
    assert _query_one(
        """
        SELECT
            COUNT(DISTINCT resource.owner_capability_code),
            COUNT(DISTINCT projection.projection_revision_id),
            COUNT(DISTINCT evidence.evidence_unit_row_id),
            COUNT(DISTINCT receipt.channel_receipt_id),
            COUNT(DISTINCT record.projection_record_id),
            COUNT(DISTINCT facet.projection_facet_id),
            COUNT(document.id)
        FROM knowledge_resources AS resource
        JOIN knowledge_resource_projections AS projection
          ON projection.knowledge_resource_id = resource.knowledge_resource_id
        JOIN knowledge_evidence_units AS evidence
          ON evidence.projection_revision_id =
             projection.projection_revision_id
        JOIN knowledge_embedding_channel_receipts AS receipt
          ON receipt.projection_revision_id =
             projection.projection_revision_id
        JOIN knowledge_projection_records AS record
          ON record.projection_revision_id =
             projection.projection_revision_id
        JOIN knowledge_projection_facets AS facet
          ON facet.projection_record_id = record.projection_record_id
        LEFT JOIN external_docs AS document
          ON document.projection_revision_id =
             projection.projection_revision_id
        WHERE resource.owner_capability_code IN (
            'synthetic_alpha', 'synthetic_beta'
        )
          AND projection.status = 'degraded_channels'
          AND receipt.state = 'not_admitted'
        """
    ) == (2, 2, 2, 2, 2, 2, 0)
