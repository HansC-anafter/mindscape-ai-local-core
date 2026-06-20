"""Selected packet node projection for memory impact graph read models."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphNode,
)
from backend.app.services.governance.memory_impact_graph_read_model_core.session_nodes import (
    has_any,
    truncate,
)


def build_selected_packet_nodes(
    *,
    workspace_id: str,
    selected_memory_packet: Dict[str, Any],
) -> List[MemoryImpactGraphNode]:
    layers = dict(selected_memory_packet.get("layers") or {})
    nodes: List[MemoryImpactGraphNode] = []

    core = dict(layers.get("core") or {})
    if has_any(core.values()):
        nodes.append(
            MemoryImpactGraphNode(
                id=f"workspace_core:{workspace_id}",
                type="memory_item",
                label="Workspace Core Memory",
                subtitle=truncate(
                    str(core.get("brand_identity") or core.get("voice_and_tone") or ""),
                    180,
                )
                or None,
                status="active",
                metadata={"packet_layer": "core", **core},
            )
        )

    _append_knowledge_nodes(nodes, layers)
    _append_goal_nodes(nodes, layers)
    _append_project_node(nodes, layers, workspace_id)
    _append_member_node(nodes, layers, workspace_id)
    _append_episodic_nodes(nodes, layers)
    return nodes


def _append_knowledge_nodes(
    nodes: List[MemoryImpactGraphNode],
    layers: Dict[str, Any],
) -> None:
    knowledge_layers = dict(layers.get("knowledge") or {})
    for bucket in ("verified", "candidates"):
        for item in list(knowledge_layers.get(bucket) or []):
            if not isinstance(item, dict):
                continue
            node_id = f"knowledge:{item.get('id')}"
            nodes.append(
                MemoryImpactGraphNode(
                    id=node_id,
                    type="knowledge",
                    label=truncate(str(item.get("content") or ""), 120) or node_id,
                    subtitle=str(item.get("knowledge_type") or "").strip() or None,
                    status=str(item.get("status") or "").strip() or None,
                    metadata={"packet_layer": f"knowledge.{bucket}", **item},
                )
            )


def _append_goal_nodes(
    nodes: List[MemoryImpactGraphNode],
    layers: Dict[str, Any],
) -> None:
    goal_layers = dict(layers.get("goals") or {})
    for bucket in ("active", "pending"):
        for item in list(goal_layers.get(bucket) or []):
            if not isinstance(item, dict):
                continue
            node_id = f"goal:{item.get('id')}"
            nodes.append(
                MemoryImpactGraphNode(
                    id=node_id,
                    type="goal",
                    label=truncate(str(item.get("title") or ""), 120) or node_id,
                    subtitle=truncate(str(item.get("description") or ""), 180) or None,
                    status=str(item.get("status") or "").strip() or None,
                    metadata={"packet_layer": f"goals.{bucket}", **item},
                )
            )


def _append_project_node(
    nodes: List[MemoryImpactGraphNode],
    layers: Dict[str, Any],
    workspace_id: str,
) -> None:
    project = dict(layers.get("project") or {})
    project_id = str(project.get("project_id") or "").strip()
    if not has_any(
        [
            project_id,
            list(project.get("decision_history") or []),
            list(project.get("key_conversations") or []),
            list(project.get("artifact_index") or []),
        ]
    ):
        return

    subtitle = ""
    decisions = list(project.get("decision_history") or [])
    if decisions and isinstance(decisions[0], dict):
        subtitle = str(decisions[0].get("decision") or "").strip()
    elif project.get("key_conversations"):
        subtitle = str((project.get("key_conversations") or [None])[0] or "").strip()
    nodes.append(
        MemoryImpactGraphNode(
            id=f"project_memory:{project_id or workspace_id}",
            type="memory_item",
            label="Project Memory",
            subtitle=truncate(subtitle, 180) or None,
            status="context",
            metadata={"packet_layer": "project", **project},
        )
    )


def _append_member_node(
    nodes: List[MemoryImpactGraphNode],
    layers: Dict[str, Any],
    workspace_id: str,
) -> None:
    member = dict(layers.get("member") or {})
    user_id = str(member.get("user_id") or "").strip()
    if not has_any(
        [
            user_id,
            list(member.get("skills") or []),
            dict(member.get("preferences") or {}),
            list(member.get("learnings") or []),
        ]
    ):
        return

    subtitle = ""
    skills = list(member.get("skills") or [])
    if skills:
        subtitle = ", ".join(str(skill) for skill in skills[:3])
    elif member.get("preferences"):
        subtitle = ", ".join(
            f"{key}={value}"
            for key, value in list(dict(member.get("preferences") or {}).items())[:2]
        )
    nodes.append(
        MemoryImpactGraphNode(
            id=f"member_memory:{workspace_id}:{user_id}",
            type="memory_item",
            label="Member Memory",
            subtitle=truncate(subtitle, 180) or None,
            status="context",
            metadata={"packet_layer": "member", **member},
        )
    )


def _append_episodic_nodes(
    nodes: List[MemoryImpactGraphNode],
    layers: Dict[str, Any],
) -> None:
    for item in list(layers.get("episodic") or []):
        if not isinstance(item, dict):
            continue
        node_id = f"memory_item:{item.get('id')}"
        nodes.append(
            MemoryImpactGraphNode(
                id=node_id,
                type="memory_item",
                label=truncate(
                    str(item.get("title") or item.get("claim") or item.get("summary") or ""),
                    120,
                )
                or node_id,
                subtitle=truncate(
                    str(item.get("summary") or item.get("claim") or ""),
                    180,
                )
                or None,
                status=str(item.get("lifecycle_status") or "").strip() or None,
                metadata={"packet_layer": "episodic", **item},
            )
        )
