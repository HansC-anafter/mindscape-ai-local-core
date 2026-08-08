from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services.authorized_knowledge_index_contracts import (
    AuthorizedIndexWriteResult,
)
from backend.app.services.knowledge_projection.approved_document_promotion import (
    ApprovedKnowledgeDocumentChunk,
    ApprovedKnowledgeDocumentPromotionCommand,
    ApprovedKnowledgeDocumentPromotionFacade,
    KnowledgePromotionReviewReceipt,
)
from backend.app.services.knowledge_projection.retrievable.canonical_json import (
    canonical_sha256,
)


def _command(reviewer="reviewer-1"):
    chunks = (
        ApprovedKnowledgeDocumentChunk(
            title="Bird evolution",
            content="Birds are living theropod dinosaurs.",
            metadata={"domain": "evolution"},
            embedding=(0.1, 0.2),
        ),
    )
    source_revision = "wiki-revision-7"
    candidate_sha256 = canonical_sha256(
        {
            "source_revision": source_revision,
            "chunks": [
                {
                    "content": chunks[0].content,
                    "title": chunks[0].title,
                    "metadata": chunks[0].metadata,
                }
            ],
            "projection_records": [],
            "owner_declared_graph": None,
        }
    )
    return ApprovedKnowledgeDocumentPromotionCommand(
        workspace_id="ws_demo",
        owner_capability_code="frontier_research",
        source_app="frontier-wiki",
        source_id="bird-evolution",
        doc_type="frontier_wiki_revision",
        source_revision=source_revision,
        chunks=chunks,
        review_receipt=KnowledgePromotionReviewReceipt(
            receipt_id="review-7",
            decision="approved",
            reviewer_user_id=reviewer,
            candidate_revision=source_revision,
            candidate_sha256=candidate_sha256,
            reviewed_at="2026-07-30T00:00:00Z",
        ),
    )


@pytest.mark.asyncio
async def test_promotion_derives_context_and_delegates_existing_writer():
    calls = {}

    class _ContextFactory:
        def build(self, auth, **kwargs):
            calls["context"] = (auth, kwargs)
            return "verified-context"

    class _Writer:
        def active_revision(self, **kwargs):
            calls["active_revision"] = kwargs
            return None

        async def replace_document(self, **kwargs):
            calls["writer"] = kwargs
            return AuthorizedIndexWriteResult(
                state="activated",
                indexed_chunks=1,
                revision_id="wiki-revision-7",
                embedding_model="fixture",
                knowledge_resource_id="resource-7",
                security_label_id="label-7",
                projection_revision_id="projection-7",
                authz_revision=4,
            )

    auth = SimpleNamespace(user_id="reviewer-1")
    receipt = await ApprovedKnowledgeDocumentPromotionFacade(
        writer=_Writer(),
        context_factory=_ContextFactory(),
    ).promote(_command(), auth=auth)

    assert calls["context"][1]["requested_workspace_ids"] == ("ws_demo",)
    assert calls["writer"]["access_context"] == "verified-context"
    assert calls["writer"]["owner_capability_code"] == "frontier_research"
    assert calls["active_revision"]["source_id"] == "bird-evolution"
    assert (
        calls["writer"]["chunks"][0].metadata[
            "promotion_review_receipt_id"
        ]
        == "review-7"
    )
    assert receipt.knowledge_resource_id == "resource-7"
    assert len(receipt.receipt_sha256) == 64


@pytest.mark.asyncio
async def test_promotion_rejects_reviewer_identity_mismatch():
    with pytest.raises(
        PermissionError,
        match="approved_knowledge_reviewer_identity_mismatch",
    ):
        await ApprovedKnowledgeDocumentPromotionFacade(
            writer=SimpleNamespace(),
            context_factory=SimpleNamespace(),
        ).promote(
            _command(reviewer="reviewer-2"),
            auth=SimpleNamespace(user_id="reviewer-1"),
        )


@pytest.mark.asyncio
async def test_promotion_rejects_active_revision_drift_before_write():
    class _Writer:
        def active_revision(self, **kwargs):
            return "wiki-revision-6"

        async def replace_document(self, **kwargs):
            raise AssertionError("drifted revision must not write")

    class _ContextFactory:
        def build(self, auth, **kwargs):
            return "verified-context"

    with pytest.raises(
        ValueError,
        match="approved_knowledge_active_revision_drift",
    ):
        await ApprovedKnowledgeDocumentPromotionFacade(
            writer=_Writer(),
            context_factory=_ContextFactory(),
        ).promote(
            _command(),
            auth=SimpleNamespace(user_id="reviewer-1"),
        )
