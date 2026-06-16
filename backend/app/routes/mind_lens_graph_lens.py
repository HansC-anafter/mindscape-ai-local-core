"""Lens, summary, link, workspace, and initialization handlers."""

import asyncio
import logging
from typing import Optional

from fastapi import HTTPException

from ..models.graph import (
    GraphNodeCategory,
    GraphNodeCreate,
    GraphNodeType,
    MindLensProfileCreate,
)
from .mind_lens_graph_models import ProfileSummaryResponse

logger = logging.getLogger(__name__)


async def list_lens_profiles_impl(store, *, profile_id: str):
    return await asyncio.to_thread(store.list_lens_profiles, profile_id)


async def get_lens_profile_impl(store, *, lens_id: str, profile_id: str):
    lens = await asyncio.to_thread(store.get_lens_profile, lens_id)

    if not lens:
        raise HTTPException(status_code=404, detail=f"Lens {lens_id} not found")

    if lens.profile_id != profile_id:
        raise HTTPException(status_code=403, detail="Lens not owned by profile")

    return lens


async def get_active_lens_impl(
    store,
    *,
    profile_id: str,
    workspace_id: Optional[str],
):
    return await asyncio.to_thread(store.get_active_lens, profile_id, workspace_id)


async def create_lens_profile_impl(
    store,
    *,
    lens: MindLensProfileCreate,
    profile_id: str,
):
    try:
        return await asyncio.to_thread(store.create_lens_profile, lens, profile_id)
    except Exception as e:
        logger.error(f"Failed to create lens profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_profile_summary_impl(store, *, profile_id: str):
    nodes = await asyncio.to_thread(
        store.list_nodes, profile_id=profile_id, is_active=True, limit=1000
    )

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
                direction["values"].append(
                    {"id": node.id, "label": node.label, "icon": node.icon or ""}
                )
            elif node.node_type == GraphNodeType.WORLDVIEW:
                direction["worldviews"].append(
                    {"id": node.id, "label": node.label, "icon": node.icon or ""}
                )
            elif node.node_type == GraphNodeType.AESTHETIC:
                direction["aesthetics"].append(
                    {"id": node.id, "label": node.label, "icon": node.icon or ""}
                )
            elif node.node_type == GraphNodeType.KNOWLEDGE:
                direction["knowledge_count"] += 1
        elif node.category == GraphNodeCategory.ACTION:
            if node.node_type == GraphNodeType.STRATEGY:
                action["strategies"].append(
                    {"id": node.id, "label": node.label, "icon": node.icon or ""}
                )
            elif node.node_type == GraphNodeType.ROLE:
                action["roles"].append(
                    {"id": node.id, "label": node.label, "icon": node.icon or ""}
                )
            elif node.node_type == GraphNodeType.RHYTHM:
                action["rhythms"].append(
                    {"id": node.id, "label": node.label, "icon": node.icon or ""}
                )

    summary_text = {
        "direction": " | ".join([v["label"] for v in direction["values"][:3]]),
        "action": " | ".join([s["label"] for s in action["strategies"][:2]]),
    }

    return ProfileSummaryResponse(
        direction=direction,
        action=action,
        summary_text=summary_text,
    )


async def link_node_to_playbook_impl(
    store,
    *,
    node_id: str,
    profile_id: str,
    playbook_code: str,
    link_type: str,
):
    try:
        await asyncio.to_thread(
            store.link_node_to_playbook, node_id, playbook_code, profile_id, link_type
        )
        return {"success": True, "message": "Playbook linked successfully"}
    except Exception as e:
        logger.error(f"Failed to link playbook: {e}")
        raise HTTPException(status_code=400, detail=str(e))


async def unlink_node_from_playbook_impl(
    store,
    *,
    node_id: str,
    playbook_code: str,
    profile_id: str,
):
    deleted = await asyncio.to_thread(
        store.unlink_node_from_playbook, node_id, playbook_code, profile_id
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Link not found")


async def bind_lens_to_workspace_impl(
    store,
    *,
    profile_id: str,
    lens_id: str,
    workspace_id: str,
):
    try:
        await asyncio.to_thread(
            store.bind_lens_to_workspace, lens_id, workspace_id, profile_id
        )
        return {"success": True, "message": "Lens bound to workspace successfully"}
    except Exception as e:
        logger.error(f"Failed to bind lens to workspace: {e}")
        raise HTTPException(status_code=400, detail=str(e))


async def unbind_lens_from_workspace_impl(
    store,
    *,
    workspace_id: str,
    profile_id: str,
):
    deleted = await asyncio.to_thread(
        store.unbind_lens_from_workspace, workspace_id, profile_id
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Binding not found")


async def initialize_graph_impl(store, *, profile_id: str):
    existing_nodes = await asyncio.to_thread(
        store.list_nodes, profile_id=profile_id, limit=1
    )
    if existing_nodes:
        all_nodes = await asyncio.to_thread(store.list_nodes, profile_id=profile_id)
        return {
            "message": "Graph already initialized",
            "node_count": len(all_nodes),
        }

    sample_nodes = [
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
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.WORLDVIEW,
            label="系統思維",
            description="用系統性的方式理解複雜問題",
            icon="🌐",
            size=1.0,
            source_type="system_init",
        ),
        GraphNodeCreate(
            category=GraphNodeCategory.DIRECTION,
            node_type=GraphNodeType.AESTHETIC,
            label="簡潔清晰",
            description="偏好簡潔、清晰的表達方式",
            icon="✨",
            size=1.0,
            source_type="system_init",
        ),
        GraphNodeCreate(
            category=GraphNodeCategory.ACTION,
            node_type=GraphNodeType.STRATEGY,
            label="迭代優化",
            description="通過小步迭代持續改進",
            icon="🔄",
            size=1.0,
            source_type="system_init",
        ),
        GraphNodeCreate(
            category=GraphNodeCategory.ACTION,
            node_type=GraphNodeType.ROLE,
            label="協作者",
            description="在團隊中扮演協作和支持的角色",
            icon="👥",
            size=1.0,
            source_type="system_init",
        ),
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
            node = await asyncio.to_thread(store.create_node, node_data, profile_id)
            created_nodes.append(node)
        except Exception as e:
            logger.error(f"Failed to create sample node: {e}")

    return {
        "message": f"Graph initialized with {len(created_nodes)} sample nodes",
        "node_count": len(created_nodes),
        "nodes": [{"id": n.id, "label": n.label} for n in created_nodes],
    }
