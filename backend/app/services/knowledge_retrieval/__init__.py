"""Authorization-aware knowledge retrieval facade exports."""

from .contracts import (
    AuthorizedKnowledgeHit,
    CitationLookup,
    FacetFilter,
    KnowledgeAggregateRequest,
    KnowledgeCitationFetchRequest,
    KnowledgeCoverageRequest,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
)
from .facade import AuthorizationAwareKnowledgeRetrievalFacade

__all__ = [
    "AuthorizationAwareKnowledgeRetrievalFacade",
    "AuthorizedKnowledgeHit",
    "CitationLookup",
    "FacetFilter",
    "KnowledgeAggregateRequest",
    "KnowledgeCitationFetchRequest",
    "KnowledgeCoverageRequest",
    "KnowledgeRetrievalRequest",
    "KnowledgeRetrievalResult",
]
