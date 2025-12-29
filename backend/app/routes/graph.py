"""
Graph API routes
RESTful API for managing Mind-Lens Graph nodes, edges, and lens profiles
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, Depends, Body
from pydantic import BaseModel

from ..models.graph import (
    GraphNode, GraphNodeCreate, GraphNodeUpdate, GraphNodeResponse,
    GraphEdge, GraphEdgeCreate, GraphEdgeUpdate,
    MindLensProfile, MindLensProfileCreate, MindLensProfileUpdate,
    GraphNodeCategory, GraphNodeType, GraphRelationType
)
from ..services.stores.graph_store import GraphStore
from ..core.deps import get_current_profile_id
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mindscape/graph", tags=["graph"])

# Initialize store
def get_graph_store() -> GraphStore:
    """Get graph store instance"""
    if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
        db_path = '/app/data/mindscape.db'
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "mindscape.db")
    return GraphStore(db_path)


# ============================================================================
# Response Models
# ============================================================================

class GraphFullResponse(BaseModel):
    """Full graph data (nodes + edges)"""
    nodes: List[GraphNodeResponse]
    edges: List[GraphEdge]


class ProfileSummaryResponse(BaseModel):
    """Profile summary for homepage"""
    direction: dict
    action: dict
    summary_text: dict


# ============================================================================
# Node API
# ============================================================================

@router.get("/nodes", response_model=List[GraphNodeResponse])
async def list_nodes(
    profile_id: str = Depends(get_current_profile_id),
    category: Optional[str] = Query(None, description="Filter by category: direction|action"),
    node_type: Optional[str] = Query(None, description="Filter by node type"),
    is_active: bool = Query(True, description="Filter by active status"),
    limit: int = Query(100, ge=1, le=1000, description="Limit results"),
):
    """List graph nodes with optional filters"""
    store = get_graph_store()

    category_enum = None
    if category:
        try:
            category_enum = GraphNodeCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    node_type_enum = None
    if node_type:
        try:
            node_type_enum = GraphNodeType(node_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid node_type: {node_type}")

    nodes = store.list_nodes(
        profile_id=profile_id,
        category=category_enum,
        node_type=node_type_enum,
        is_active=is_active,
        limit=limit,
    )

    # Populate linked fields from bridge tables
    result = []
    for node in nodes:
        node_dict = node.dict()
        node_dict['linked_entity_ids'] = []
        node_dict['linked_playbook_codes'] = store.get_node_linked_playbooks(node.id)
        node_dict['linked_intent_ids'] = []
        result.append(GraphNodeResponse(**node_dict))

    return result


@router.get("/nodes/{node_id}", response_model=GraphNodeResponse)
async def get_node(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Get a single graph node"""
    store = get_graph_store()
    node = store.get_node(node_id)

    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    if node.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Node not owned by profile")

    node_dict = node.dict()
    node_dict['linked_entity_ids'] = []
    node_dict['linked_playbook_codes'] = store.get_node_linked_playbooks(node_id)
    node_dict['linked_intent_ids'] = []
    return GraphNodeResponse(**node_dict)


@router.post("/nodes", response_model=GraphNode, status_code=201)
async def create_node(
    node: GraphNodeCreate,
    profile_id: str = Depends(get_current_profile_id),
):
    """Create a new graph node"""
    store = get_graph_store()
    try:
        created = store.create_node(node, profile_id)
        return created
    except Exception as e:
        logger.error(f"Failed to create node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/nodes/{node_id}", response_model=GraphNode)
async def update_node(
    node_id: str = Path(..., description="Node ID"),
    updates: GraphNodeUpdate = ...,
    profile_id: str = Depends(get_current_profile_id),
):
    """Update a graph node"""
    store = get_graph_store()
    updated = store.update_node(node_id, profile_id, updates)

    if not updated:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    return updated


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Depends(get_current_profile_id),
    cascade: bool = Query(False, description="Cascade delete edges"),
):
    """Delete a graph node"""
    store = get_graph_store()
    deleted = store.delete_node(node_id, profile_id, cascade=cascade)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")


# ============================================================================
# Edge API
# ============================================================================

@router.get("/edges", response_model=List[GraphEdge])
async def list_edges(
    profile_id: str = Depends(get_current_profile_id),
    source_node_id: Optional[str] = Query(None, description="Filter by source node"),
    target_node_id: Optional[str] = Query(None, description="Filter by target node"),
    relation_type: Optional[str] = Query(None, description="Filter by relation type"),
):
    """List graph edges with optional filters"""
    store = get_graph_store()

    relation_type_enum = None
    if relation_type:
        try:
            relation_type_enum = GraphRelationType(relation_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid relation_type: {relation_type}")

    edges = store.list_edges(
        profile_id=profile_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type_enum,
    )

    return edges


@router.post("/edges", response_model=GraphEdge, status_code=201)
async def create_edge(
    edge: GraphEdgeCreate,
    profile_id: str = Depends(get_current_profile_id),
):
    """Create a new graph edge"""
    store = get_graph_store()
    try:
        created = store.create_edge(edge, profile_id)
        return created
    except Exception as e:
        logger.error(f"Failed to create edge: {e}")
        if "not found" in str(e).lower() or "not owned" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(
    edge_id: str = Path(..., description="Edge ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Delete a graph edge"""
    store = get_graph_store()
    deleted = store.delete_edge(edge_id, profile_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found")


# ============================================================================
# Full Graph API
# ============================================================================

@router.get("/full", response_model=GraphFullResponse)
async def get_full_graph(
    profile_id: str = Depends(get_current_profile_id),
    workspace_id: Optional[str] = Query(None, description="Workspace ID for active lens"),
):
    """Get full graph data (nodes + edges) with active lens applied"""
    store = get_graph_store()

    # Get active lens if workspace_id provided
    active_lens = None
    if workspace_id:
        active_lens = store.get_active_lens(profile_id, workspace_id)

    # Get all nodes
    nodes = store.list_nodes(profile_id=profile_id, is_active=True, limit=1000)

    # Filter by active lens if applicable
    if active_lens and active_lens.active_node_ids:
        active_node_ids = set(active_lens.active_node_ids)
        nodes = [n for n in nodes if n.id in active_node_ids]

    # Get all edges for these nodes
    node_ids = {n.id for n in nodes}
    all_edges = store.list_edges(profile_id=profile_id)
    edges = [e for e in all_edges if e.source_node_id in node_ids and e.target_node_id in node_ids]

    # Populate linked fields
    result_nodes = []
    for node in nodes:
        node_dict = node.dict()
        node_dict['linked_entity_ids'] = []
        node_dict['linked_playbook_codes'] = store.get_node_linked_playbooks(node.id)
        node_dict['linked_intent_ids'] = []
        result_nodes.append(GraphNodeResponse(**node_dict))

    return GraphFullResponse(nodes=result_nodes, edges=edges)


# ============================================================================
# Lens Profile API
# ============================================================================

@router.get("/lens/profiles", response_model=List[MindLensProfile])
async def list_lens_profiles(
    profile_id: str = Depends(get_current_profile_id),
):
    """List all lens profiles for a profile"""
    store = get_graph_store()
    return store.list_lens_profiles(profile_id)


@router.get("/lens/profiles/{lens_id}", response_model=MindLensProfile)
async def get_lens_profile(
    lens_id: str = Path(..., description="Lens ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Get a lens profile"""
    store = get_graph_store()
    lens = store.get_lens_profile(lens_id)

    if not lens:
        raise HTTPException(status_code=404, detail=f"Lens {lens_id} not found")

    if lens.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Lens not owned by profile")

    return lens


@router.get("/lens/active", response_model=Optional[MindLensProfile])
async def get_active_lens(
    profile_id: str = Depends(get_current_profile_id),
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
):
    """Get active lens for profile/workspace"""
    store = get_graph_store()
    return store.get_active_lens(profile_id, workspace_id)


@router.post("/lens/profiles", response_model=MindLensProfile, status_code=201)
async def create_lens_profile(
    lens: MindLensProfileCreate,
    profile_id: str = Depends(get_current_profile_id),
):
    """Create a new lens profile"""
    store = get_graph_store()
    try:
        created = store.create_lens_profile(lens, profile_id)
        return created
    except Exception as e:
        logger.error(f"Failed to create lens profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Profile Summary API (for homepage)
# ============================================================================

@router.get("/profile-summary", response_model=ProfileSummaryResponse)
async def get_profile_summary(
    profile_id: str = Depends(get_current_profile_id),
):
    """Get profile summary for homepage MindProfileCard"""
    store = get_graph_store()

    # Get all active nodes
    nodes = store.list_nodes(profile_id=profile_id, is_active=True, limit=1000)

    # Group by category and type
    direction = {
        "values": [],
        "worldviews": [],
        "aesthetics": [],
        "knowledge_count": 0,
    }
    action = {
        "strategies": [],
        "roles": [],
        "rhythms": [],
    }

    for node in nodes:
        if node.category == GraphNodeCategory.DIRECTION:
            if node.node_type == GraphNodeType.VALUE:
                direction["values"].append({"id": node.id, "label": node.label, "icon": node.icon or ""})
            elif node.node_type == GraphNodeType.WORLDVIEW:
                direction["worldviews"].append({"id": node.id, "label": node.label, "icon": node.icon or ""})
            elif node.node_type == GraphNodeType.AESTHETIC:
                direction["aesthetics"].append({"id": node.id, "label": node.label, "icon": node.icon or ""})
            elif node.node_type == GraphNodeType.KNOWLEDGE:
                direction["knowledge_count"] += 1
        elif node.category == GraphNodeCategory.ACTION:
            if node.node_type == GraphNodeType.STRATEGY:
                action["strategies"].append({"id": node.id, "label": node.label, "icon": node.icon or ""})
            elif node.node_type == GraphNodeType.ROLE:
                action["roles"].append({"id": node.id, "label": node.label, "icon": node.icon or ""})
            elif node.node_type == GraphNodeType.RHYTHM:
                action["rhythms"].append({"id": node.id, "label": node.label, "icon": node.icon or ""})

    # Build summary text
    summary_text = {
        "direction": " | ".join([v["label"] for v in direction["values"][:3]]),
        "action": " | ".join([s["label"] for s in action["strategies"][:2]]),
    }

    return ProfileSummaryResponse(
        direction=direction,
        action=action,
        summary_text=summary_text,
    )


# ============================================================================
# Playbook Links API
# ============================================================================

@router.post("/nodes/{node_id}/link-playbook", status_code=201)
async def link_node_to_playbook(
    node_id: str = Path(..., description="Node ID"),
    profile_id: str = Depends(get_current_profile_id),
    playbook_code: str = Body(..., description="Playbook code"),
    link_type: str = Body("applies", description="Link type: applies/excludes"),
):
    """Link node to playbook"""
    store = get_graph_store()
    try:
        store.link_node_to_playbook(node_id, playbook_code, profile_id, link_type)
        return {"success": True, "message": "Playbook linked successfully"}
    except Exception as e:
        logger.error(f"Failed to link playbook: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/nodes/{node_id}/link-playbook/{playbook_code}", status_code=204)
async def unlink_node_from_playbook(
    node_id: str = Path(..., description="Node ID"),
    playbook_code: str = Path(..., description="Playbook code"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Unlink node from playbook"""
    store = get_graph_store()
    deleted = store.unlink_node_from_playbook(node_id, playbook_code, profile_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Link not found")


# ============================================================================
# Workspace Bindings API
# ============================================================================

@router.post("/lens/bind-workspace", status_code=201)
async def bind_lens_to_workspace(
    profile_id: str = Depends(get_current_profile_id),
    lens_id: str = Query(..., description="Lens ID"),
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """Bind lens to workspace"""
    store = get_graph_store()
    try:
        store.bind_lens_to_workspace(lens_id, workspace_id, profile_id)
        return {"success": True, "message": "Lens bound to workspace successfully"}
    except Exception as e:
        logger.error(f"Failed to bind lens to workspace: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/lens/unbind-workspace/{workspace_id}", status_code=204)
async def unbind_lens_from_workspace(
    workspace_id: str = Path(..., description="Workspace ID"),
    profile_id: str = Depends(get_current_profile_id),
):
    """Unbind lens from workspace"""
    store = get_graph_store()
    deleted = store.unbind_lens_from_workspace(workspace_id, profile_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Binding not found")


# ============================================================================
# Initialization API
# ============================================================================

@router.post("/initialize", status_code=201)
async def initialize_graph(
    profile_id: str = Depends(get_current_profile_id),
):
    """
    Initialize graph with sample nodes for new users
    Creates a basic set of nodes to help users get started
    """
    store = get_graph_store()

    # Check if user already has nodes
    existing_nodes = store.list_nodes(profile_id=profile_id, limit=1)
    if existing_nodes:
        return {"message": "Graph already initialized", "node_count": len(store.list_nodes(profile_id=profile_id))}

    # Sample nodes based on mock data structure
    sample_nodes = [
        # Direction - Values
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.VALUE,
            label="不剝削合作對象",
            description="與合作夥伴的關係要互惠，不做單方面獲利的事",
            icon="🤝",
            size=1.0,
            source_type="system_init",
        ),
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.VALUE,
            label="不做黑箱",
            description="保持透明，讓合作方了解過程和決策",
            icon="🔍",
            size=1.0,
            source_type="system_init",
        ),
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.VALUE,
            label="對學習者誠實",
            description="在教學和分享時，不隱瞞限制和不足",
            icon="💬",
            size=1.0,
            source_type="system_init",
        ),
        # Direction - Worldviews
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.WORLDVIEW,
            label="系統思維",
            description="用系統性的方式理解複雜問題",
            icon="🌐",
            size=1.0,
            source_type="system_init",
        ),
        # Direction - Aesthetics
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.AESTHETIC,
            label="簡潔清晰",
            description="偏好簡潔、清晰的表達方式",
            icon="✨",
            size=1.0,
            source_type="system_init",
        ),
        # Action - Strategy
        GraphNodeCreate(
            category=GraphNodeCategory.ACTION,
            node_type=GraphNodeType.STRATEGY,
            label="迭代優化",
            description="通過小步迭代持續改進",
            icon="🔄",
            size=1.0,
            source_type="system_init",
        ),
        # Action - Role
        GraphNodeCreate(
            category=GraphNodeCategory.ACTION,
            node_type=GraphNodeType.ROLE,
            label="協作者",
            description="在團隊中扮演協作和支持的角色",
            icon="👥",
            size=1.0,
            source_type="system_init",
        ),
        # Action - Rhythm
        GraphNodeCreate(
            category=GraphNodeCategory.ACTION,
            node_type=GraphNodeType.RHYTHM,
            label="深度工作",
            description="偏好長時間專注的深度工作模式",
            icon="⏰",
            size=1.0,
            source_type="system_init",
        ),
    ]

    created_nodes = []
    for node_data in sample_nodes:
        try:
            node = store.create_node(node_data, profile_id)
            created_nodes.append(node)
        except Exception as e:
            logger.error(f"Failed to create sample node: {e}")

    return {
        "message": f"Graph initialized with {len(created_nodes)} sample nodes",
        "node_count": len(created_nodes),
        "nodes": [{"id": n.id, "label": n.label} for n in created_nodes],
    }

