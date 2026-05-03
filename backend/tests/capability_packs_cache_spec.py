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
