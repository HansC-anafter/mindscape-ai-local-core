"""Facade for authorization-aware bounded graph candidate stores."""

from __future__ import annotations

from .query_store_global import AuthorizationAwareKnowledgeGraphGlobalMixin
from .query_store_neighborhood import (
    AuthorizationAwareKnowledgeGraphNeighborhoodMixin,
)


class AuthorizationAwareKnowledgeGraphQueryStore(
    AuthorizationAwareKnowledgeGraphNeighborhoodMixin,
    AuthorizationAwareKnowledgeGraphGlobalMixin,
):
    """Keep one public query store while SQL responsibilities remain leaves."""

    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory


__all__ = ["AuthorizationAwareKnowledgeGraphQueryStore"]
