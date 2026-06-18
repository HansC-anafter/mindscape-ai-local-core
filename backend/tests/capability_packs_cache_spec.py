from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
import time

from backend.tests.capability_packs_cache_support import (
    _reset_pack_yaml_cache,
    capability_packs,
)
from backend.app.routes.core.capability_packs_core import cache_state
from backend.app.services.capability_pack_route_cache import (
    clear_installed_capability_metadata_caches,
)


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
    _reset_pack_yaml_cache()
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


def test_get_capability_ui_components_caches_success_payload(monkeypatch):
    _reset_pack_yaml_cache()
    calls = {"installed": 0, "meta": 0}
    pack_meta = {
        "id": "demo_pack",
        "code": "demo_pack",
        "ui_components": [
            {
                "code": "DemoPage",
                "path": "ui/components/DemoPage.tsx",
                "description": "Cached demo",
                "export": "default",
            }
        ],
    }

    def fake_get_pack_meta_by_code(capability_code):
        calls["meta"] += 1
        return pack_meta

    def fake_get_installed_pack_ids():
        calls["installed"] += 1
        return {"demo_pack"}

    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        fake_get_pack_meta_by_code,
    )
    monkeypatch.setattr(
        capability_packs,
        "_get_installed_pack_ids",
        fake_get_installed_pack_ids,
    )
    monkeypatch.setattr(
        capability_packs._installed_routes,
        "_get_runtime_ui_component",
        lambda capability_code, component_code: {},
    )

    first = capability_packs.get_capability_ui_components("demo_pack")
    first[0]["description"] = "mutated"
    second = capability_packs.get_capability_ui_components("demo_pack")

    assert calls == {"installed": 1, "meta": 1}
    assert second[0]["description"] == "Cached demo"


def test_get_capability_mobile_workbench_gateway_support_formats_runtime_manifest(
    monkeypatch,
):
    _reset_pack_yaml_cache()
    monkeypatch.setattr(
        capability_packs,
        "_get_pack_meta_by_code",
        lambda capability_code: {
            "id": "yogacoach",
            "code": "yogacoach",
            "display_name": "YogaCoach",
            "ui_components": [
                {
                    "code": "YogaPracticeWorkbenchPage",
                    "path": "ui/workbench/practice/YogaPracticeWorkbenchPage.tsx",
                    "description": "Yoga practice workbench",
                    "export": "default",
                }
            ],
            "apis": [
                {"prefix": "/api/v1/capabilities/yogacoach"},
                {"prefix": "/api/v1/capabilities/yogacoach"},
            ],
        },
    )
    monkeypatch.setattr(
        capability_packs, "_get_installed_pack_ids", lambda: {"yogacoach"}
    )

    payload = capability_packs.get_capability_mobile_workbench_gateway_support(
        "yogacoach"
    )

    assert payload["capability_code"] == "yogacoach"
    assert payload["supported"] is True
    assert (
        payload["host_route_template"]
        == "/workspaces/{workspaceId}/capability-ui-hosts/yogacoach"
    )
    assert payload["main_page_component_codes"] == ["YogaPracticeWorkbenchPage"]
    assert payload["api_prefixes"] == ["/api/v1/capabilities/yogacoach"]


def test_get_installed_pack_ids_caches_store_lookup(monkeypatch):
    _reset_pack_yaml_cache()
    calls = 0

    def fake_list_installed_pack_ids():
        nonlocal calls
        calls += 1
        return ["demo_pack", "dance_motion_coach"]

    monkeypatch.setattr(
        capability_packs._manifest_scan.installed_packs_store,
        "list_installed_pack_ids",
        fake_list_installed_pack_ids,
    )

    first = capability_packs._get_installed_pack_ids()
    second = capability_packs._get_installed_pack_ids()

    assert first == {"demo_pack", "dance_motion_coach"}
    assert second == {"demo_pack", "dance_motion_coach"}
    assert calls == 1


def test_get_pack_meta_by_code_caches_default_lookup(monkeypatch, tmp_path):
    _reset_pack_yaml_cache()
    manifest_dir = tmp_path / "app" / "capabilities" / "demo_pack"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "manifest.yaml"
    manifest_path.write_text(
        """
code: demo_pack
display_name: Demo Pack
version: 0.2.0
description: Runtime manifest lookup smoke.
ui_components:
  - code: DemoPage
    path: ui/components/DemoPage.tsx
""",
        encoding="utf-8",
    )

    candidate_calls = 0

    def fake_candidate_paths(capability_code, base_dir=None):
        nonlocal candidate_calls
        candidate_calls += 1
        return [(manifest_path, "capability_manifest", "demo_pack")]

    monkeypatch.setattr(
        capability_packs._manifest_scan,
        "_candidate_pack_manifest_paths",
        fake_candidate_paths,
    )
    monkeypatch.setattr(
        capability_packs._manifest_scan,
        "_scan_pack_yaml_files",
        lambda base_dir=None: [],
    )

    first = capability_packs._get_pack_meta_by_code("demo-pack")
    second = capability_packs._get_pack_meta_by_code("demo-pack")

    assert first is not None
    assert second is not None
    assert first["id"] == "demo_pack"
    assert second["id"] == "demo_pack"
    assert candidate_calls == 1


def test_runtime_ui_index_cache_deduplicates_component_lookup(monkeypatch, tmp_path):
    _reset_pack_yaml_cache()
    calls = 0
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("code: demo_pack\n", encoding="utf-8")
    (tmp_path / "ui_runtime_assets.json").write_text(
        """
{
  "components": [
    {"code": "DemoOne", "asset_url": "/one.js"},
    {"code": "DemoTwo", "asset_url": "/two.js"}
  ]
}
""",
        encoding="utf-8",
    )

    def fake_get_pack_meta_by_code(capability_code):
        nonlocal calls
        calls += 1
        return {"_file_path": str(manifest_path)}

    monkeypatch.setattr(
        capability_packs._installed_routes,
        "_get_pack_meta_by_code",
        fake_get_pack_meta_by_code,
    )

    first = capability_packs._installed_routes._get_runtime_ui_component(
        "demo_pack",
        "DemoOne",
    )
    second = capability_packs._installed_routes._get_runtime_ui_component(
        "demo_pack",
        "DemoTwo",
    )

    assert calls == 1
    assert first["asset_url"] == "/one.js"
    assert second["asset_url"] == "/two.js"


def test_clear_installed_capability_metadata_caches_invalidates_route_state():
    _reset_pack_yaml_cache()
    cache_state.set_cached_capability_route_payload(
        "ui-components",
        "demo_pack",
        [{"code": "DemoPage"}],
    )
    cache_state.set_cached_runtime_ui_index(
        "demo_pack",
        {"components": [{"code": "DemoPage", "asset_url": "/old.js"}]},
    )
    cache_state.set_cached_installed_pack_ids({"demo_pack"})
    cache_state.set_cached_pack_meta_by_code("demo_pack", {"id": "demo_pack"})

    assert cache_state.get_cached_capability_route_payload("ui-components", "demo_pack")
    assert cache_state.get_cached_runtime_ui_index("demo_pack")
    assert cache_state.get_cached_installed_pack_ids() == {"demo_pack"}
    assert cache_state.get_cached_pack_meta_by_code("demo_pack")

    cleared = clear_installed_capability_metadata_caches(
        capability_code="demo_pack",
        reason="test",
    )

    assert cleared >= 1
    assert cache_state.get_cached_capability_route_payload("ui-components", "demo_pack") is None
    assert cache_state.get_cached_runtime_ui_index("demo_pack") is None
    assert cache_state.get_cached_installed_pack_ids() is None
    assert cache_state.get_cached_pack_meta_by_code("demo_pack") is None
