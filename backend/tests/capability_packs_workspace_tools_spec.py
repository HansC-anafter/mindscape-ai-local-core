from backend.tests.capability_packs_cache_support import capability_packs


def test_get_capability_workspace_tools_joins_panel_component(monkeypatch):
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "demo_pack",
            "code": "demo_pack",
            "ui_components": [
                {
                    "code": "DemoToolPanel",
                    "path": "ui/DemoToolPanel.tsx",
                    "description": "Tool panel",
                    "export": "default",
                },
            ],
            "workspace_tools": [
                {
                    "id": "demo_tool",
                    "group": "capability",
                    "label": "Demo Tool",
                    "icon": "PanelRight",
                    "order": 5,
                    "panel_component_code": "DemoToolPanel",
                }
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    tools = capability_packs.get_capability_workspace_tools("demo_pack")

    assert tools == [
        {
            "tool_key": "demo_pack:demo_tool",
            "capability_code": "demo_pack",
            "id": "demo_tool",
            "group": "capability",
            "slot": "workspace.right_rail.tool",
            "label": "Demo Tool",
            "icon": "PanelRight",
            "order": 5,
            "panel_component_code": "DemoToolPanel",
            "panel_component": {
                "code": "DemoToolPanel",
                "path": "ui/DemoToolPanel.tsx",
                "description": "Tool panel",
                "export": "default",
                "artifact_types": [],
                "playbook_codes": [],
                "import_path": "@/app/capabilities/demo_pack/components/DemoToolPanel",
                "layout_hint": "default",
            },
        }
    ]


def test_get_capability_workspace_tools_formats_slot_runtime_metadata(monkeypatch):
    pack_meta = {
        "id": "ig",
        "code": "ig",
        "ui_components": [
            {
                "code": "FeedGridLoadToolPanel",
                "path": "ui/workbench/feedGridTool/FeedGridLoadToolPanel.tsx",
                "export": "FeedGridLoadToolPanel",
                "description": "Feed load panel",
            }
        ],
        "tools": [
            {
                "code": "ig_query_references",
                "planner_contract": {
                    "exposed": True,
                    "consumers": ["meeting_engine"],
                },
            }
        ],
        "workspace_tools": [
            {
                "id": "feed_grid_card_load_limit",
                "group": "capability",
                "slot": "workbench.left_tool_rail",
                "label": "Feed Load",
                "icon": "SlidersHorizontal",
                "panel_component_code": "FeedGridLoadToolPanel",
                "order": 10,
                "shortcut": "B",
                "runtime_tool_code": "ig_query_references",
                "aol": {
                    "object_kind": "tool",
                    "object_uri": "mindscape://ig/tool/feed_grid_card_load_limit",
                    "role": "constraint",
                },
                "state_schema": {
                    "load_limit": {
                        "type": "integer",
                        "min": 1,
                        "max": 300,
                    }
                },
            }
        ],
    }

    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: pack_meta,
    )
    monkeypatch.setattr(capability_packs, "_get_installed_pack_ids", lambda: {"ig"})

    [tool] = capability_packs.get_capability_workspace_tools("ig")

    assert tool["tool_key"] == "ig:feed_grid_card_load_limit"
    assert tool["slot"] == "workbench.left_tool_rail"
    assert tool["shortcut"] == "B"
    assert tool["runtime_tool_code"] == "ig_query_references"
    assert tool["aol"] == {
        "object_kind": "tool",
        "object_uri": "mindscape://ig/tool/feed_grid_card_load_limit",
        "role": "constraint",
    }
    assert tool["state_schema"]["load_limit"]["max"] == 300
    assert tool["panel_component"]["code"] == "FeedGridLoadToolPanel"


def test_get_capability_workspace_tools_rejects_unexposed_runtime_tool(monkeypatch):
    pack_meta = {
        "id": "ig",
        "code": "ig",
        "ui_components": [
            {
                "code": "FeedGridLoadToolPanel",
                "path": "ui/workbench/feedGridTool/FeedGridLoadToolPanel.tsx",
            }
        ],
        "tools": [
            {
                "code": "ig_query_references",
                "planner_contract": {"exposed": False},
            }
        ],
        "workspace_tools": [
            {
                "id": "feed_grid_card_load_limit",
                "group": "capability",
                "slot": "workbench.left_tool_rail",
                "label": "Feed Load",
                "icon": "SlidersHorizontal",
                "panel_component_code": "FeedGridLoadToolPanel",
                "order": 10,
                "runtime_tool_code": "ig_query_references",
            }
        ],
    }

    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: pack_meta,
    )
    monkeypatch.setattr(capability_packs, "_get_installed_pack_ids", lambda: {"ig"})

    try:
        capability_packs.get_capability_workspace_tools("ig")
    except capability_packs.HTTPException as exc:
        assert exc.status_code == 422
        assert "planner_contract" in exc.detail
    else:
        raise AssertionError("Expected unexposed runtime tool to be rejected")


def test_get_capability_workspace_tools_rejects_invalid_panel_reference(monkeypatch):
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "demo_pack",
            "code": "demo_pack",
            "ui_components": [],
            "workspace_tools": [
                {
                    "id": "demo_tool",
                    "group": "capability",
                    "label": "Demo Tool",
                    "icon": "PanelRight",
                    "order": 5,
                    "panel_component_code": "MissingPanel",
                }
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    try:
        capability_packs.get_capability_workspace_tools("demo_pack")
    except capability_packs.HTTPException as exc:
        assert exc.status_code == 422
        assert "panel_component_code" in exc.detail
    else:
        raise AssertionError("Expected invalid workspace tool panel reference to fail")


def test_get_capability_workspace_tools_rejects_invalid_id_and_order(monkeypatch):
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "demo_pack",
            "code": "demo_pack",
            "ui_components": [
                {
                    "code": "DemoToolPanel",
                    "path": "ui/DemoToolPanel.tsx",
                },
            ],
            "workspace_tools": [
                {
                    "id": "Demo-Tool",
                    "group": "capability",
                    "label": "Demo Tool",
                    "order": "5",
                    "panel_component_code": "DemoToolPanel",
                }
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    try:
        capability_packs.get_capability_workspace_tools("demo_pack")
    except capability_packs.HTTPException as exc:
        assert exc.status_code == 422
        assert "workspace_tools[0].id" in exc.detail
    else:
        raise AssertionError("Expected invalid workspace tool id to fail")


def test_get_capability_workspace_tools_rejects_missing_icon(monkeypatch):
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "demo_pack",
            "code": "demo_pack",
            "ui_components": [
                {
                    "code": "DemoToolPanel",
                    "path": "ui/DemoToolPanel.tsx",
                },
            ],
            "workspace_tools": [
                {
                    "id": "demo_tool",
                    "group": "capability",
                    "label": "Demo Tool",
                    "order": 5,
                    "panel_component_code": "DemoToolPanel",
                }
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    try:
        capability_packs.get_capability_workspace_tools("demo_pack")
    except capability_packs.HTTPException as exc:
        assert exc.status_code == 422
        assert "workspace_tools[0].icon" in exc.detail
    else:
        raise AssertionError("Expected missing workspace tool icon to fail")


def test_get_capability_workspace_tools_rejects_bool_order(monkeypatch):
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "demo_pack",
            "code": "demo_pack",
            "ui_components": [
                {
                    "code": "DemoToolPanel",
                    "path": "ui/DemoToolPanel.tsx",
                },
            ],
            "workspace_tools": [
                {
                    "id": "demo_tool",
                    "group": "capability",
                    "label": "Demo Tool",
                    "icon": "PanelRight",
                    "order": True,
                    "panel_component_code": "DemoToolPanel",
                }
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    try:
        capability_packs.get_capability_workspace_tools("demo_pack")
    except capability_packs.HTTPException as exc:
        assert exc.status_code == 422
        assert "workspace_tools[0].order" in exc.detail
    else:
        raise AssertionError("Expected boolean workspace tool order to fail")
