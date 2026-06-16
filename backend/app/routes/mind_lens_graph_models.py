"""Response models for Mind-Lens graph routes."""

from typing import List

from pydantic import BaseModel

from ..models.graph import GraphEdge, GraphNodeResponse


class GraphFullResponse(BaseModel):
    """Full graph data (nodes + edges)."""

    nodes: List[GraphNodeResponse]
    edges: List[GraphEdge]


class ProfileSummaryResponse(BaseModel):
    """Profile summary for homepage."""

    direction: dict
    action: dict
    summary_text: dict
