"""Public subordinate exports for retrievable knowledge projection."""

from .adapter_descriptor import KnowledgeProjectionAdapterDescriptor
from .adapter_registry import (
    KnowledgeProjectionAdapterRegistry,
    get_adapter_registry,
    register_manifest,
    resolve_descriptor,
)
from .contracts import (
    EvidenceRelation,
    PortableFacet,
    PortableRecord,
    ProjectionChannelReceipt,
    ProjectionCitation,
    ProjectionReceipt,
    RetrievableProjectionEnvelope,
    RetrievableSourceRef,
)
from .embedding_channels import (
    EmbeddingChannelRequest,
    EmbeddingChannelResult,
    KnowledgeEmbeddingChannel,
    KnowledgeEmbeddingChannelDescriptor,
    TextEmbeddingChannel,
)
from .evidence_units import (
    AudioTimeRangeAnchor,
    DerivativeRef,
    EvidenceUnit,
    ImageRegionAnchor,
    TextSpanAnchor,
    VideoTimeRangeAnchor,
)

__all__ = [
    "AudioTimeRangeAnchor",
    "DerivativeRef",
    "EmbeddingChannelRequest",
    "EmbeddingChannelResult",
    "EvidenceRelation",
    "EvidenceUnit",
    "ImageRegionAnchor",
    "KnowledgeEmbeddingChannel",
    "KnowledgeEmbeddingChannelDescriptor",
    "KnowledgeProjectionAdapterDescriptor",
    "KnowledgeProjectionAdapterRegistry",
    "PortableFacet",
    "PortableRecord",
    "ProjectionChannelReceipt",
    "ProjectionCitation",
    "ProjectionReceipt",
    "RetrievableProjectionEnvelope",
    "RetrievableSourceRef",
    "TextEmbeddingChannel",
    "TextSpanAnchor",
    "VideoTimeRangeAnchor",
    "get_adapter_registry",
    "register_manifest",
    "resolve_descriptor",
]
