"""Node, edge, and full graph handlers for Mind-Lens graph routes."""

import asyncio
import logging
from typing import Optional

from fastapi import HTTPException

from ..models.graph import (
    GraphEdgeCreate,
    GraphNodeCategory,
    GraphNodeCreate,
    GraphNodeResponse,
    GraphNodeType,
    GraphNodeUpdate,
    GraphRelationType,
)
from .mind_lens_graph_models import GraphFullResponse

logger = logging.getLogger(__name__)


async def _node_response(store, node):
    node_dict = node.model_dump()
    node_dict["linked_entity_ids"] = []
    node_dict["linked_playbook_codes"] = await asyncio.to_thread(
        store.get_node_linked_playbooks, node.id
    )
    node_dict["linked_intent_ids"] = []
    return GraphNodeResponse(**node_dict)


async def list_nodes_impl(
    store,
    *,
    profile_id: str,
    category: Optional[str],
    node_type: Optional[str],
    is_active: bool,
    limit: int,
):
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
            raise HTTPException(
                status_code=400, detail=f"Invalid node_type: {node_type}"
            )

    nodes = await asyncio.to_thread(
        store.list_nodes,
        profile_id=profile_id,
        category=category_enum,
        node_type=node_type_enum,
        is_active=is_active,
        limit=limit,
    )

    result = []
    for node in nodes:
        result.append(await _node_response(store, node))
    return result


async def get_node_impl(store, *, node_id: str, profile_id: str):
    node = await asyncio.to_thread(store.get_node, node_id)

    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    if node.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Node not owned by profile")

    return await _node_response(store, node)


async def create_node_impl(store, *, node: GraphNodeCreate, profile_id: str):
    try:
        return await asyncio.to_thread(store.create_node, node, profile_id)
    except Exception as e:
        logger.error(f"Failed to create node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def update_node_impl(
    store,
    *,
    node_id: str,
    profile_id: str,
    updates: GraphNodeUpdate,
):
    updated = await asyncio.to_thread(store.update_node, node_id, profile_id, updates)

    if not updated:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    return updated


async def delete_node_impl(
    store,
    *,
    node_id: str,
    profile_id: str,
    cascade: bool,
):
    deleted = await asyncio.to_thread(store.delete_node, node_id, profile_id, cascade)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")


async def list_edges_impl(
    store,
    *,
    profile_id: str,
    source_node_id: Optional[str],
    target_node_id: Optional[str],
    relation_type: Optional[str],
):
    relation_type_enum = None
    if relation_type:
        try:
            relation_type_enum = GraphRelationType(relation_type)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid relation_type: {relation_type}"
            )

    return await asyncio.to_thread(
        store.list_edges,
        profile_id=profile_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type_enum,
    )


async def create_edge_impl(store, *, edge: GraphEdgeCreate, profile_id: str):
    try:
        return await asyncio.to_thread(store.create_edge, edge, profile_id)
    except Exception as e:
        logger.error(f"Failed to create edge: {e}")
        if "not found" in str(e).lower() or "not owned" in str(e).lower():
            raise HTTPException(status_code=400, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def delete_edge_impl(store, *, edge_id: str, profile_id: str):
    deleted = await asyncio.to_thread(store.delete_edge, edge_id, profile_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Edge {edge_id} not found")


async def get_full_graph_impl(
    store,
    *,
    profile_id: str,
    workspace_id: Optional[str],
):
    active_lens = None
    if workspace_id:
        active_lens = await asyncio.to_thread(
            store.get_active_lens, profile_id, workspace_id
        )

    nodes = await asyncio.to_thread(
        store.list_nodes, profile_id=profile_id, is_active=True, limit=1000
    )

    if active_lens and active_lens.active_node_ids:
        active_node_ids = set(active_lens.active_node_ids)
        nodes = [n for n in nodes if n.id in active_node_ids]

    node_ids = {n.id for n in nodes}
    all_edges = await asyncio.to_thread(store.list_edges, profile_id=profile_id)
    edges = [
        e
        for e in all_edges
        if e.source_node_id in node_ids and e.target_node_id in node_ids
    ]

    result_nodes = []
    for node in nodes:
        result_nodes.append(await _node_response(store, node))

    return GraphFullResponse(nodes=result_nodes, edges=edges)
