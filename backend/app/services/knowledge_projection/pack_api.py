"""Stable capability-pack API for retrievable knowledge projection.

Capability code imports this facade only. Internal storage, authorization,
queue, and graph modules remain Local Core implementation details.
"""

from .approved_document_promotion import (
    ApprovedKnowledgeDocumentChunk,
    ApprovedKnowledgeDocumentPromotionCommand,
    ApprovedKnowledgeDocumentPromotionFacade,
    ApprovedKnowledgeDocumentPromotionReceipt,
    KnowledgePromotionReviewReceipt,
)
from .retrievable.pack_compiler_support import (
    EmbeddingProvider,
    ObjectResolver,
    compile_owner_object_projection,
)
from .retrievable.task_payload import (
    DescriptorPointer,
    KnowledgeProjectionTaskPayload,
    SourcePointer,
)

__all__ = [
    "ApprovedKnowledgeDocumentChunk",
    "ApprovedKnowledgeDocumentPromotionCommand",
    "ApprovedKnowledgeDocumentPromotionFacade",
    "ApprovedKnowledgeDocumentPromotionReceipt",
    "DescriptorPointer",
    "EmbeddingProvider",
    "KnowledgeProjectionTaskPayload",
    "KnowledgePromotionReviewReceipt",
    "ObjectResolver",
    "SourcePointer",
    "compile_owner_object_projection",
]
