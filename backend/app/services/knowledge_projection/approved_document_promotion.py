"""Stable reviewed-document promotion seam for capability packs."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalAccessContextFactory,
)

from .legacy_document_facade import (
    AuthorizedLegacyDocumentFacade,
    LegacyDocumentChunk,
)
from .retrievable.canonical_json import canonical_sha256


class ApprovedKnowledgeDocumentChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1, max_length=100_000)
    title: str = Field(min_length=1, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: tuple[float, ...] = Field(default=(), max_length=8192)


class KnowledgePromotionReviewReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str = Field(min_length=1, max_length=256)
    decision: Literal["approved"]
    reviewer_user_id: str = Field(min_length=1, max_length=128)
    candidate_revision: str = Field(min_length=1, max_length=256)
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_at: str = Field(min_length=1, max_length=64)


class ApprovedKnowledgeDocumentPromotionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1, max_length=128)
    owner_capability_code: str = Field(
        pattern=r"^[a-z0-9_]+$",
        max_length=128,
    )
    source_app: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=256)
    doc_type: str = Field(min_length=1, max_length=128)
    source_revision: str = Field(min_length=1, max_length=256)
    expected_active_revision: str | None = Field(
        default=None,
        max_length=256,
    )
    owner_scope_type: Literal["workspace", "group"] = "workspace"
    owner_scope_id: str | None = Field(default=None, max_length=128)
    chunks: tuple[ApprovedKnowledgeDocumentChunk, ...] = Field(
        min_length=1,
        max_length=128,
    )
    projection_records: tuple[dict[str, Any], ...] = Field(
        default=(),
        max_length=512,
    )
    owner_declared_graph: dict[str, Any] | None = None
    review_receipt: KnowledgePromotionReviewReceipt

    @model_validator(mode="after")
    def validate_scope_and_candidate_identity(self):
        expected_scope_id = self.owner_scope_id or self.workspace_id
        if (
            self.owner_scope_type == "workspace"
            and expected_scope_id != self.workspace_id
        ):
            raise ValueError(
                "approved_knowledge_workspace_scope_id_mismatch"
            )
        candidate_sha256 = canonical_sha256(
            {
                "source_revision": self.source_revision,
                "chunks": [
                    {
                        "content": chunk.content,
                        "title": chunk.title,
                        "metadata": chunk.metadata,
                    }
                    for chunk in self.chunks
                ],
                "projection_records": list(self.projection_records),
                "owner_declared_graph": self.owner_declared_graph,
            }
        )
        if self.review_receipt.candidate_revision != self.source_revision:
            raise ValueError(
                "approved_knowledge_review_revision_mismatch"
            )
        if self.review_receipt.candidate_sha256 != candidate_sha256:
            raise ValueError("approved_knowledge_candidate_hash_mismatch")
        return self


class ApprovedKnowledgeDocumentPromotionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str
    workspace_id: str
    owner_scope_type: Literal["workspace", "group"]
    owner_scope_id: str
    source_revision: str
    candidate_sha256: str
    review_receipt_id: str
    knowledge_resource_id: str
    security_label_id: str
    projection_revision_id: str
    authz_revision: int
    indexed_chunks: int
    receipt_sha256: str = ""

    @model_validator(mode="after")
    def add_receipt_hash(self):
        if self.receipt_sha256:
            return self
        payload = self.model_dump(
            mode="json",
            exclude={"receipt_sha256"},
        )
        object.__setattr__(
            self,
            "receipt_sha256",
            canonical_sha256(payload),
        )
        return self


class ApprovedKnowledgeDocumentPromotionFacade:
    """Validate human approval, derive ACL truth, and delegate one writer."""

    def __init__(
        self,
        *,
        writer: AuthorizedLegacyDocumentFacade | None = None,
        context_factory: RetrievalAccessContextFactory | None = None,
    ) -> None:
        self._writer = writer or AuthorizedLegacyDocumentFacade()
        self._context_factory = (
            context_factory or RetrievalAccessContextFactory()
        )

    async def promote(
        self,
        command: ApprovedKnowledgeDocumentPromotionCommand,
        *,
        auth: Any,
    ) -> ApprovedKnowledgeDocumentPromotionReceipt:
        reviewer = str(getattr(auth, "user_id", "") or "").strip()
        if reviewer != command.review_receipt.reviewer_user_id:
            raise PermissionError(
                "approved_knowledge_reviewer_identity_mismatch"
            )
        scope_id = command.owner_scope_id or command.workspace_id
        access_context = self._context_factory.build(
            auth,
            requested_workspace_ids=(
                (command.workspace_id,)
                if command.owner_scope_type == "workspace"
                else ()
            ),
            requested_group_ids=(
                (scope_id,)
                if command.owner_scope_type == "group"
                else ()
            ),
        )
        active_revision = self._writer.active_revision(
            access_context=access_context,
            workspace_id=command.workspace_id,
            owner_capability_code=command.owner_capability_code,
            source_app=command.source_app,
            source_id=command.source_id,
        )
        if active_revision != command.expected_active_revision:
            raise ValueError(
                "approved_knowledge_active_revision_drift"
            )
        written = await self._writer.replace_document(
            access_context=access_context,
            workspace_id=command.workspace_id,
            owner_capability_code=command.owner_capability_code,
            source_app=command.source_app,
            source_id=command.source_id,
            doc_type=command.doc_type,
            chunks=tuple(
                LegacyDocumentChunk(
                    content=chunk.content,
                    title=chunk.title,
                    metadata={
                        **dict(chunk.metadata),
                        "promotion_review_receipt_id": (
                            command.review_receipt.receipt_id
                        ),
                        "promotion_candidate_sha256": (
                            command.review_receipt.candidate_sha256
                        ),
                    },
                    embedding=chunk.embedding,
                )
                for chunk in command.chunks
            ),
            source_revision=command.source_revision,
            owner_scope_type=command.owner_scope_type,
            owner_scope_id=scope_id,
            projection_records=command.projection_records,
            owner_declared_graph=command.owner_declared_graph,
        )
        return ApprovedKnowledgeDocumentPromotionReceipt(
            state=written.state,
            workspace_id=command.workspace_id,
            owner_scope_type=command.owner_scope_type,
            owner_scope_id=scope_id,
            source_revision=written.revision_id,
            candidate_sha256=command.review_receipt.candidate_sha256,
            review_receipt_id=command.review_receipt.receipt_id,
            knowledge_resource_id=written.knowledge_resource_id,
            security_label_id=written.security_label_id,
            projection_revision_id=written.projection_revision_id,
            authz_revision=written.authz_revision,
            indexed_chunks=written.indexed_chunks,
        )


__all__ = [
    "ApprovedKnowledgeDocumentChunk",
    "ApprovedKnowledgeDocumentPromotionCommand",
    "ApprovedKnowledgeDocumentPromotionFacade",
    "ApprovedKnowledgeDocumentPromotionReceipt",
    "KnowledgePromotionReviewReceipt",
]
