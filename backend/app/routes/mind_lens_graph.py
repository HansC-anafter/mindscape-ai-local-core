"""
Graph API routes
RESTful API for managing Mind-Lens Graph nodes, edges, and lens profiles
"""

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Path, Query

from ..core.deps import get_current_profile_id
from ..models.graph import (
    GraphEdge,
    GraphEdgeCreate,
    GraphNode,
    GraphNodeCreate,
    GraphNodeResponse,
    GraphNodeUpdate,
    MindLensProfile,
    MindLensProfileCreate,
)
from ..services.stores.graph_store import GraphStore
from .mind_lens_graph_lens import (
    bind_lens_to_workspace_impl,
    create_lens_profile_impl,
    get_active_lens_impl,
    get_lens_profile_impl,
    get_profile_summary_impl,
    initialize_graph_impl,
    link_node_to_playbook_impl,
    list_lens_profiles_impl,
    unbind_lens_from_workspace_impl,
    unlink_node_from_playbook_impl,
)
from .mind_lens_graph_models import GraphFullResponse, ProfileSummaryResponse
from .mind_lens_graph_nodes import (
    create_edge_impl,
    create_node_impl,
    delete_edge_impl,
    delete_node_impl,
    get_full_graph_impl,
    get_node_impl,
    list_edges_impl,
    list_nodes_impl,
    update_node_impl,
)

router = APIRouter(prefix="/api/v1/mind-lens/graph", tags=["mind-lens-graph"])


def get_graph_store() -> GraphStore:
    """Get graph store instance"""
    return GraphStore()


@router.get("/nodes", response_model=List[GraphNodeResponse])
async def list_nodes(
    profile_id: str = Depends(get_current_profile_id),
    category: Optional[str] = Query(
        None, description="Filter by category: direction|action"
    ),
    node_type: Optional[str] = Query(None, description="Filter by node type"),
    is_active: bool = Query(True, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
):
    """List graph nodes with optional filters"""
    store = get_graph_store()
    return await list_nodes_impl(
        store,
        profile_id=profile_id,
        category=category,
        node_type=node_type,
        is_active=is_active,
        limit=limit,
    )


@router.get("/nodes/{node_id}", response_model=GraphNodeResponse)
async def get_node(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Get a single graph node"""
    store = get_graph_store()
    return await get_node_impl(store, node_id=node_id, profile_id=profile_id)


@router.post("/nodes", response_model=GraphNode, status_code=201)
async def create_node(
    node: GraphNodeCreate,
    profile_id: str = Depends(get_current_profile_id),
):
    """Create a new graph node"""
    store = get_graph_store()
    return await create_node_impl(store, node=node, profile_id=profile_id)


@router.put("/nodes/{node_id}", response_model=GraphNode)
async def update_node(
    node_id: str = Path(..., description="Node ID"),
    updates: GraphNodeUpdate = ...,
    profile_id: str = Depends(get_current_profile_id),
):
    """Update a graph node"""
    store = get_graph_store()
    return await update_node_impl(
        store, node_id=node_id, profile_id=profile_id, updates=updates
    )


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Depends(get_current_profile_id),
    cascade: bool = Query(False, description="Cascade delete edges"),
):
    """Delete a graph node"""
    store = get_graph_store()
    return await delete_node_impl(
        store, node_id=node_id, profile_id=profile_id, cascade=cascade
    )


@router.get("/edges", response_model=List[GraphEdge])
async def list_edges(
    profile_id: str = Depends(get_current_profile_id),
    source_node_id: Optional[str] = Query(None, description="Filter by source node"),
    target_node_id: Optional[str] = Query(None, description="Filter by target node"),
    relation_type: Optional[str] = Query(None, description="Filter by relation type"),
):
    """List graph edges with optional filters"""
    store = get_graph_store()
    return await list_edges_impl(
        store,
        profile_id=profile_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
    )


@router.post("/edges", response_model=GraphEdge, status_code=201)
async def create_edge(
    edge: GraphEdgeCreate,
    profile_id: str = Depends(get_current_profile_id),
):
    """Create a new graph edge"""
    store = get_graph_store()
    return await create_edge_impl(store, edge=edge, profile_id=profile_id)


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: str = Path(..., description="Edge ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Delete a graph edge"""
    store = get_graph_store()
    return await delete_edge_impl(store, edge_id=edge_id, profile_id=profile_id)


@router.get("/full", response_model=GraphFullResponse)
async def get_full_graph(
    profile_id: str = Depends(get_current_profile_id),
    workspace_id: Optional[str] = Query(
        None, description="Workspace ID for active lens"
    ),
):
    """Get full graph data (nodes + edges) with active lens applied"""
    store = get_graph_store()
    return await get_full_graph_impl(
        store, profile_id=profile_id, workspace_id=workspace_id
    )


@router.get("/lens/profiles", response_model=List[MindLensProfile])
async def list_lens_profiles(
    profile_id: str = Depends(get_current_profile_id),
):
    """List all lens profiles for a profile"""
    store = get_graph_store()
    return await list_lens_profiles_impl(store, profile_id=profile_id)


@router.get("/lens/profiles/{lens_id}", response_model=MindLensProfile)
async def get_lens_profile(
    lens_id: str = Path(..., description="Lens ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Get a lens profile"""
    store = get_graph_store()
    return await get_lens_profile_impl(store, lens_id=lens_id, profile_id=profile_id)


@router.get("/lens/active", response_model=Optional[MindLensProfile])
async def get_active_lens(
    profile_id: str = Depends(get_current_profile_id),
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
):
    """Get active lens for profile/workspace"""
    store = get_graph_store()
    return await get_active_lens_impl(
        store, profile_id=profile_id, workspace_id=workspace_id
    )


@router.post("/lens/profiles", response_model=MindLensProfile, status_code=201)
async def create_lens_profile(
    lens: MindLensProfileCreate,
    profile_id: str = Depends(get_current_profile_id),
):
    """Create a new lens profile"""
    store = get_graph_store()
    return await create_lens_profile_impl(store, lens=lens, profile_id=profile_id)


@router.get("/profile-summary", response_model=ProfileSummaryResponse)
async def get_profile_summary(
    profile_id: str = Depends(get_current_profile_id),
):
    """Get profile summary for homepage MindProfileCard"""
    store = get_graph_store()
    return await get_profile_summary_impl(store, profile_id=profile_id)


@router.post("/nodes/{node_id}/link-playbook", status_code=201)
async def link_node_to_playbook(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Depends(get_current_profile_id),
    playbook_code: str = Body(..., description="Playbook code"),
    link_type: str = Body("applies", description="Link type: applies/excludes"),
):
    """Link node to playbook"""
    store = get_graph_store()
    return await link_node_to_playbook_impl(
        store,
        node_id=node_id,
        profile_id=profile_id,
        playbook_code=playbook_code,
        link_type=link_type,
    )


@router.delete("/nodes/{node_id}/link-playbook/{playbook_code}", status_code=204)
async def unlink_node_from_playbook(
    node_id: str = Path(..., description="Node ID"),
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Unlink node from playbook"""
    store = get_graph_store()
    return await unlink_node_from_playbook_impl(
        store, node_id=node_id, playbook_code=playbook_code, profile_id=profile_id
    )


@router.post("/lens/bind-workspace", status_code=201)
async def bind_lens_to_workspace(
    profile_id: str = Depends(get_current_profile_id),
    lens_id: str = Query(..., description="Lens ID"),
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Bind lens to workspace"""
    store = get_graph_store()
    return await bind_lens_to_workspace_impl(
        store, profile_id=profile_id, lens_id=lens_id, workspace_id=workspace_id
    )


@router.delete("/lens/unbind-workspace/{workspace_id}", status_code=204)
async def unbind_lens_from_workspace(
    workspace_id: str = Path(..., description="Workspace ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Unbind lens from workspace"""
    store = get_graph_store()
    return await unbind_lens_from_workspace_impl(
        store, workspace_id=workspace_id, profile_id=profile_id
    )


@router.post("/initialize", status_code=201)
async def initialize_graph(
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Initialize graph with sample nodes for new users
    Creates a basic set of nodes to help users get started
    """
    store = get_graph_store()
    return await initialize_graph_impl(store, profile_id=profile_id)
