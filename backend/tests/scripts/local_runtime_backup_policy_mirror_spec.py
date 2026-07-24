import importlib.util
import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


incremental = _load_module(
    "local_runtime_incremental_backup",
    REPO_ROOT / "scripts" / "local_runtime_incremental_backup.py",
)


def test_capacity_preflight_does_not_double_count_existing_wal_on_primary(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    data = tmp_path / "data"
    wal_root = primary / "postgres-wal-archive"
    for path in [primary, mirror, data / "postgres", wal_root]:
        path.mkdir(parents=True)

    def fake_dir_size(path):
        if path == data / "postgres":
            return 100
        if path == wal_root:
            return 1000
        return 0

    monkeypatch.setattr(incremental, "resolve_data_host_dir", lambda: data)
    monkeypatch.setattr(incremental, "estimate_snapshot_transfer_bytes", lambda *_args, **_kwargs: 10)
    monkeypatch.setattr(incremental, "estimate_mirror_snapshot_transfer_bytes", lambda *_args, **_kwargs: 20)
    monkeypatch.setattr(incremental, "disk_usage_bytes", fake_dir_size)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 10_000)

    result = incremental.capacity_preflight(
        plan={"base_backup_required": True, "wal_archive_bytes": 1000},
        config={
            "primary_root": primary,
            "mirror_root": mirror,
            "wal_archive_root": wal_root,
            "min_free_gb": 0,
            "mirror_scopes": ["postgres_chain"],
        },
        previous_manifest=None,
        previous_snapshot=None,
        timeout_seconds=30,
    )

    assert result["primary_estimated_required_bytes"] == 110
    assert result["mirror_estimated_required_bytes"] == 1120


def test_postgres_only_capacity_skips_runtime_snapshot_and_mirror_estimates(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    data = tmp_path / "data"
    wal_root = primary / "postgres-wal-archive"
    for path in [primary, data / "postgres", wal_root]:
        path.mkdir(parents=True)

    monkeypatch.setattr(incremental, "resolve_data_host_dir", lambda: data)
    monkeypatch.setattr(
        incremental,
        "estimate_snapshot_transfer_bytes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("postgres-only must not estimate app-data")
        ),
    )
    monkeypatch.setattr(incremental, "disk_usage_bytes", lambda path: 100 if path == data / "postgres" else 1000)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 10_000)

    result = incremental.capacity_preflight(
        plan={"base_backup_required": True, "wal_archive_bytes": 1000},
        config={
            "primary_root": primary,
            "mirror_root": None,
            "wal_archive_root": wal_root,
            "min_free_gb": 0,
            "mirror_scopes": [],
            "postgres_only": True,
        },
        previous_manifest=None,
        previous_snapshot=None,
        timeout_seconds=30,
    )

    assert result["backup_scope"] == "postgres_chain_only"
    assert result["snapshot_transfer_bytes"] == 0
    assert result["primary_estimated_required_bytes"] == 100
    assert result["mirror_estimated_required_bytes"] == 0


def test_mirror_incremental_artifacts_skips_legacy_backups_and_rewrites_manifest(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    wal_root = primary / "postgres-wal-archive"
    base_id = "base_20260520T000000Z"
    backup_dir = primary / "incremental_20260520T010000Z"
    legacy_dir = primary / "legacy-full-backup"
    segment = "000000010000000000000001"

    (backup_dir / "app-data" / "runtime").mkdir(parents=True)
    (backup_dir / "app-data" / "runtime" / "payload.txt").write_text("payload\n", encoding="utf-8")
    (backup_dir / "app-data" / "secrets" / "storage").mkdir(parents=True)
    (backup_dir / "app-data" / "secrets" / "storage" / "blob.bin").write_text("blob\n", encoding="utf-8")
    (wal_root / "base_backups" / base_id).mkdir(parents=True)
    (wal_root / "base_backups" / base_id / "PG_VERSION").write_text("16\n", encoding="utf-8")
    (wal_root / segment).write_text("wal\n", encoding="utf-8")
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "legacy.bin").write_text("legacy\n", encoding="utf-8")
    incremental.latest_pointer(primary).parent.mkdir(parents=True)
    incremental.latest_pointer(primary).write_text(
        json.dumps({"latest_backup_name": backup_dir.name, "latest_backup_dir": str(backup_dir)}) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "2.0",
        "mode": "incremental_runtime_backup",
        "backup_name": backup_dir.name,
        "created_at": "2026-05-20T01:00:00Z",
        "backup_dir": str(backup_dir),
        "components": {
            "postgres": {
                "base_backup_id": base_id,
                "base_backup_dir": str(wal_root / "base_backups" / base_id),
                "wal_archive_dir": str(wal_root),
                "wal_segments": [segment],
            },
            "files": {"snapshot_relpath": "app-data"},
        },
        "verification": {"primary": "passed", "mirror": "pending"},
    }
    incremental.write_json(backup_dir / "manifest.json", manifest)

    def fake_run_capture(cmd, timeout=None):
        source = Path(cmd[-2].rstrip("/"))
        target = Path(cmd[-1].rstrip("/"))
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if "--delete-excluded" in cmd:
            runtime_source = source / "runtime"
            if runtime_source.exists():
                shutil.copytree(runtime_source, target / "runtime", dirs_exist_ok=True)
        else:
            shutil.copytree(source, target, dirs_exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(incremental, "run_capture", fake_run_capture)

    result = incremental.mirror_incremental_artifacts(
        primary_root=primary,
        mirror_root=mirror,
        backup_dir=backup_dir,
        wal_root=wal_root,
        manifest=manifest,
        timeout_seconds=30,
        retention_count=3,
        mirror_scopes=["postgres_chain", "runtime_metadata", "auth_state"],
    )

    mirror_manifest = json.loads((mirror / backup_dir.name / "manifest.json").read_text(encoding="utf-8"))
    mirror_wal_root = mirror / "postgres-wal-archive"
    assert result["verify"]["success"] is True
    assert not (mirror / legacy_dir.name).exists()
    assert mirror_manifest["backup_dir"] == str(mirror / backup_dir.name)
    assert mirror_manifest["components"]["postgres"]["base_backup_dir"] == str(
        mirror_wal_root / "base_backups" / base_id
    )
    assert mirror_manifest["components"]["postgres"]["wal_archive_dir"] == str(mirror_wal_root)
    assert (mirror_wal_root / "base_backups" / base_id / "PG_VERSION").is_file()
    assert (mirror_wal_root / segment).is_file()
    assert (mirror / backup_dir.name / "app-data" / "runtime" / "payload.txt").is_file()
    assert not (mirror / backup_dir.name / "app-data" / "secrets" / "storage" / "blob.bin").exists()
