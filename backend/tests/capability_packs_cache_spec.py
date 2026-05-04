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
