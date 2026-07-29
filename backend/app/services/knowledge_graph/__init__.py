"""Authorization-inheriting graph materialization and query components."""

from .authorization_binding import bind_graph_visibility
from .community import build_visibility_partitioned_communities
from .contracts import (
    GraphCommunityReportWrite,
    GraphEntityWrite,
    GraphMentionWrite,
    GraphProjectionWrite,
    GraphRelationWrite,
)
from .resolution import canonical_entity_key

__all__ = [
    "GraphCommunityReportWrite",
    "GraphEntityWrite",
    "GraphMentionWrite",
    "GraphProjectionWrite",
    "GraphRelationWrite",
    "bind_graph_visibility",
    "build_visibility_partitioned_communities",
    "canonical_entity_key",
]
"""Pack-neutral GraphRAG leaves.

Import concrete services from their owning modules so contract imports do not
eagerly construct the retrieval stack.
"""

__all__: list[str] = []
