"""
Vector Search Tool

Provides vector search capabilities for Playbooks.
"""

from typing import Dict, Any, List, Optional
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema
from backend.app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)


class VectorSearchTool(MindscapeTool):
    """Vector search tool for semantic search across external documents"""

    def __init__(self):
        self.vector_service = VectorSearchService()
        metadata = ToolMetadata(
            name="vector_search.search_external_docs",
            description="Search external documents using semantic search",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "query": {
                        "type": "string",
                        "description": "Search query text"
                    },
                    "source_apps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by source apps (e.g., ['content-vault'])",
                        "default": []
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID for filtering",
                        "default": "default_user"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5
                    },
                    "filters": {
                        "type": "object",
                        "description": "Additional metadata filters (e.g., {'series_id': 'xxx'})",
                        "default": {}
                    }
                },
                required=["query"]
            ),
            category="data",
            source_type="builtin",
            provider="vector_search",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        query: str,
        source_apps: Optional[List[str]] = None,
        user_id: str = "default_user",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search external documents using semantic search

        Args:
            query: Search query text
            source_apps: Filter by source apps
            user_id: User ID for filtering
            top_k: Number of results
            filters: Additional metadata filters

        Returns:
            List of matching documents with similarity scores
        """
        try:
            results = await self.vector_service.search_external_docs(
                query=query,
                source_apps=source_apps or [],
                user_id=user_id,
                top_k=top_k
            )

            if filters:
                filtered_results = []
                for result in results:
                    metadata = result.get('metadata', {})
                    if isinstance(metadata, str):
                        import json
                        try:
                            metadata = json.loads(metadata)
                        except:
                            metadata = {}

                    match = True
                    for key, value in filters.items():
                        if metadata.get(key) != value:
                            match = False
                            break

                    if match:
                        filtered_results.append(result)

                return filtered_results[:top_k]

            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []





