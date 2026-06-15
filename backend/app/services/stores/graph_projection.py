from typing import Any, Callable, Dict, Iterable, Optional

from app.models.graph import (
    GraphEdge,
    GraphNode,
    GraphNodeCategory,
    GraphNodeType,
    GraphRelationType,
    LensNodeState,
    LensProfileNode,
    MindLensProfile,
    WorkspaceLensOverride,
)


DeserializeJson = Callable[[Any, Dict[str, Any]], Dict[str, Any]]


def row_data(row) -> Dict[str, Any]:
    return row._mapping if hasattr(row, "_mapping") else row


def row_to_node(row, deserialize_json: DeserializeJson) -> GraphNode:
    data = row_data(row)
    return GraphNode(
        id=data["id"],
        profile_id=data["profile_id"],
        category=GraphNodeCategory(data["category"]),
        node_type=GraphNodeType(data["node_type"]),
        label=data["label"],
        description=data["description"],
        content=data["content"],
        icon=data["icon"],
        color=data["color"],
        size=data["size"],
        is_active=bool(data["is_active"]),
        confidence=data["confidence"],
        source_type=data["source_type"],
        source_id=data["source_id"],
        metadata=deserialize_json(data["metadata"], {}),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def row_to_edge(row, deserialize_json: DeserializeJson) -> GraphEdge:
    data = row_data(row)
    return GraphEdge(
        id=data["id"],
        profile_id=data["profile_id"],
        source_node_id=data["source_node_id"],
        target_node_id=data["target_node_id"],
        relation_type=GraphRelationType(data["relation_type"]),
        weight=data["weight"],
        label=data["label"],
        is_active=bool(data["is_active"]),
        metadata=deserialize_json(data["metadata"], {}),
        created_at=data["created_at"],
    )


def row_to_lens(
    row,
    *,
    active_node_ids: list[str],
    linked_workspace_ids: list[str],
) -> MindLensProfile:
    data = row_data(row)
    return MindLensProfile(
        id=data["id"],
        profile_id=data["profile_id"],
        name=data["name"],
        description=data["description"],
        is_default=bool(data["is_default"]),
        active_node_ids=active_node_ids,
        linked_workspace_ids=linked_workspace_ids,
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def row_to_lens_profile_node(row) -> LensProfileNode:
    data = row_data(row)
    return LensProfileNode(
        id=data["id"],
        preset_id=data["preset_id"],
        node_id=data["node_id"],
        state=LensNodeState(data["state"]),
        updated_at=data["updated_at"],
    )


def row_to_workspace_override(row) -> WorkspaceLensOverride:
    data = row_data(row)
    return WorkspaceLensOverride(
        id=data["id"],
        workspace_id=data["workspace_id"],
        node_id=data["node_id"],
        state=LensNodeState(data["state"]),
        updated_at=data["updated_at"],
    )


def rows_to_workspace_override_state_map(
    rows: Iterable[Any],
) -> Optional[Dict[str, LensNodeState]]:
    values = {
        row_data(row)["node_id"]: LensNodeState(row_data(row)["state"])
        for row in rows
    }
    return values or None
