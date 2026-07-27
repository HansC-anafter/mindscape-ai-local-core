"""One public benchmark store composed from bounded SQL leaves."""

from backend.app.services.vector_search import VectorSearchService

from .store_cache import KnowledgeBenchmarkCacheStoreMixin
from .store_catalog import KnowledgeBenchmarkCatalogStoreMixin


class KnowledgeBenchmarkStore(
    KnowledgeBenchmarkCatalogStoreMixin,
    KnowledgeBenchmarkCacheStoreMixin,
):
    def __init__(self, vector_service: VectorSearchService | None = None):
        service = vector_service or VectorSearchService()
        self._connection_factory = service._get_connection


__all__ = ["KnowledgeBenchmarkStore"]
