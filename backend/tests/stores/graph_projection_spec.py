import json
from datetime import datetime, timezone

from app.models.graph import (
    GraphNodeCategory,
    GraphNodeType,
    GraphRelationType,
    LensNodeState,
)
from app.services.stores.graph_projection import (
    row_to_edge,
    row_to_lens,
    row_to_lens_profile_node,
    row_to_node,
    row_to_workspace_override,
    rows_to_workspace_override_state_map,
)
from app.services.stores.graph_store import GraphStore


class Row:
    def __init__(self, data):
        self._mapping = data


def _deserialize(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def test_row_to_node_and_edge_preserve_enums_and_metadata():
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    node = row_to_node(
        Row(
            {
                "id": "node-1",
                "profile_id": "profile-1",
                "category": "direction",
                "node_type": "value",
                "label": "Quality",
                "description": "Deep work",
                "content": "Prefer fewer moving pieces",
                "icon": "dot",
                "color": "#123456",
                "size": 1.5,
                "is_active": 1,
                "confidence": 0.9,
                "source_type": "user_input",
                "source_id": "source-1",
                "metadata": '{"priority": "high"}',
                "created_at": now,
                "updated_at": now,
            }
        ),
        _deserialize,
    )
    edge = row_to_edge(
        {
            "id": "edge-1",
            "profile_id": "profile-1",
            "source_node_id": "node-1",
            "target_node_id": "node-2",
            "relation_type": "supports",
            "weight": 0.7,
            "label": "supports",
            "is_active": True,
            "metadata": {"source": "test"},
            "created_at": now,
        },
        _deserialize,
    )

    assert node.category is GraphNodeCategory.DIRECTION
    assert node.node_type is GraphNodeType.VALUE
    assert node.metadata == {"priority": "high"}
    assert edge.relation_type is GraphRelationType.SUPPORTS
    assert edge.metadata == {"source": "test"}


def test_row_to_lens_uses_store_supplied_relationships():
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    lens = row_to_lens(
        {
            "id": "lens-1",
            "profile_id": "profile-1",
            "name": "Focus",
            "description": "Focus lens",
            "is_default": 1,
            "created_at": now,
            "updated_at": now,
        },
        active_node_ids=["node-1"],
        linked_workspace_ids=["workspace-1"],
    )

    assert lens.is_default is True
    assert lens.active_node_ids == ["node-1"]
    assert lens.linked_workspace_ids == ["workspace-1"]


def test_lens_node_and_workspace_override_projection():
    now = datetime(2026, 6, 16, tzinfo=timezone.utc)
    profile_node = row_to_lens_profile_node(
        {
            "id": "lpn-1",
            "preset_id": "lens-1",
            "node_id": "node-1",
            "state": "emphasize",
            "updated_at": now,
        }
    )
    override = row_to_workspace_override(
        {
            "id": "override-1",
            "workspace_id": "workspace-1",
            "node_id": "node-1",
            "state": "off",
            "updated_at": now,
        }
    )
    state_map = rows_to_workspace_override_state_map(
        [
            {"node_id": "node-1", "state": "keep"},
            {"node_id": "node-2", "state": "off"},
        ]
    )

    assert profile_node.state is LensNodeState.EMPHASIZE
    assert override.state is LensNodeState.OFF
    assert state_map == {
        "node-1": LensNodeState.KEEP,
        "node-2": LensNodeState.OFF,
    }


def test_graph_store_entrypoint_keeps_public_method_surface():
    assert [cls.__name__ for cls in GraphStore.__mro__[:4]] == [
        "GraphStore",
        "GraphNodeEdgeMixin",
        "GraphLensMixin",
        "PostgresStoreBase",
    ]
    for method_name in (
        "create_node",
        "list_nodes",
        "create_edge",
        "create_lens_profile",
        "bind_lens_to_workspace",
        "set_workspace_override",
    ):
        assert callable(getattr(GraphStore, method_name))
