from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
import time

from backend.app.routes.core import capability_packs


def _reset_pack_yaml_cache():
    capability_packs._pack_yaml_cache = None
    capability_packs._pack_yaml_cache_time = 0


def test_pack_yaml_scan_cache_deduplicates_concurrent_default_scans(monkeypatch):
    _reset_pack_yaml_cache()
    calls = 0
    calls_lock = Lock()
    barrier = Barrier(8)

    def fake_uncached_scan(base_dir=None):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return [{"id": "ig"}]

    monkeypatch.setattr(
        capability_packs, "_scan_pack_yaml_files_uncached", fake_uncached_scan
    )

    def scan():
        barrier.wait()
        return capability_packs._scan_pack_yaml_files()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: scan(), range(8)))

    assert calls == 1
    assert results == [[{"id": "ig"}]] * 8


def test_pack_yaml_scan_cache_does_not_apply_to_explicit_base_dir(monkeypatch, tmp_path):
    _reset_pack_yaml_cache()
    capability_packs._pack_yaml_cache = [{"id": "cached"}]
    capability_packs._pack_yaml_cache_time = time.time()
    calls = []

    def fake_uncached_scan(base_dir=None):
        calls.append(base_dir)
        return [{"id": "explicit"}]

    monkeypatch.setattr(
        capability_packs, "_scan_pack_yaml_files_uncached", fake_uncached_scan
    )

    assert capability_packs._scan_pack_yaml_files(Path(tmp_path)) == [
        {"id": "explicit"}
    ]
    assert calls == [Path(tmp_path)]


def test_get_pack_meta_by_code_reads_runtime_manifest_without_full_scan(tmp_path):
    _reset_pack_yaml_cache()
    manifest_dir = tmp_path / "app" / "capabilities" / "demo_pack"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.yaml").write_text(
        """
code: demo_pack
display_name: Demo Pack
version: 0.2.0
description: Runtime manifest lookup smoke.
ui_components:
  - name: DemoPage
    component_path: components/DemoPage.tsx
""",
        encoding="utf-8",
    )

    pack_meta = capability_packs._get_pack_meta_by_code("demo-pack", tmp_path)

    assert pack_meta is not None
    assert pack_meta["id"] == "demo_pack"
    assert pack_meta["code"] == "demo_pack"
    assert pack_meta["name"] == "Demo Pack"
    assert pack_meta["version"] == "0.2.0"
    assert pack_meta["ui_components"][0]["name"] == "DemoPage"


def test_pack_meta_merge_deduplicates_structured_routes():
    merged = capability_packs._merge_unique_items(
        [{"module": "demo.routes", "router": "router"}],
        [
            {"module": "demo.routes", "router": "router"},
            {"module": "other.routes", "router": "router"},
        ],
    )

    assert merged == [
        {"module": "demo.routes", "router": "router"},
        {"module": "other.routes", "router": "router"},
    ]


def test_get_installed_capability_rejects_uninstalled_pack(monkeypatch, tmp_path):
    _reset_pack_yaml_cache()
    manifest_dir = tmp_path / "app" / "capabilities" / "demo_pack"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.yaml").write_text(
        """
code: demo_pack
display_name: Demo Pack
ui_components: []
""",
        encoding="utf-8",
    )

    original_get_pack_meta = capability_packs._get_pack_meta_by_code
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: original_get_pack_meta(capability_code, tmp_path),
    )
    monkeypatch.setattr(capability_packs, "_get_installed_pack_ids", lambda: set())

    try:
        capability_packs.get_installed_capability("demo-pack")
    except capability_packs.HTTPException as exc:
        assert exc.status_code == 404
        assert "is not installed" in exc.detail
    else:
        raise AssertionError("Expected uninstalled capability to be rejected")


def test_get_installed_capability_formats_runtime_manifest(monkeypatch, tmp_path):
    _reset_pack_yaml_cache()
    manifest_dir = tmp_path / "app" / "capabilities" / "demo_pack"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.yaml").write_text(
        """
code: demo_pack
display_name: Demo Pack
version: 0.2.0
description: Runtime manifest lookup smoke.
ui_components:
  - name: DemoPage
    component_path: components/DemoPage.tsx
""",
        encoding="utf-8",
    )

    original_get_pack_meta = capability_packs._get_pack_meta_by_code
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: original_get_pack_meta(capability_code, tmp_path),
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    response = capability_packs.get_installed_capability("demo-pack")

    assert response.status_code == 200
    assert response.body
    assert b'"id":"demo_pack"' in response.body
    assert b'"display_name":"Demo Pack"' in response.body


def test_get_capability_ui_components_returns_layout_hint(monkeypatch):
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "demo_pack",
            "code": "demo_pack",
            "ui_components": [
                {
                    "code": "DemoFullBleedPage",
                    "path": "ui/components/DemoFullBleedPage.tsx",
                    "description": "Full bleed demo",
                    "export": "default",
                    "layout_hint": "scrollable_full_bleed",
                },
                {
                    "code": "DemoDefaultPage",
                    "path": "ui/components/DemoDefaultPage.tsx",
                    "description": "Default demo",
                    "export": "default",
                },
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"demo_pack"}
    )

    components = capability_packs.get_capability_ui_components("demo_pack")

    assert components[0]["layout_hint"] == "scrollable_full_bleed"
    assert components[1]["layout_hint"] == "default"


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
