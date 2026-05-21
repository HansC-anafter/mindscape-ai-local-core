import importlib.util
import json
from argparse import Namespace
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


def _args(**overrides):
    values = {
        "output_dir": None,
        "mirror_root": None,
        "retention_local_count": None,
        "retention_mirror_count": None,
        "min_free_gb": None,
        "require_mirror": None,
        "base_interval_hours": None,
    }
    values.update(overrides)
    return Namespace(**values)


def test_policy_plan_is_fixed_to_incremental_runtime_backup(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    mirror = tmp_path / "mirror"
    wal_root = primary / "postgres-wal-archive"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", str(mirror))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_RETENTION_LOCAL_COUNT", "5")
    monkeypatch.setenv("LOCAL_CORE_BACKUP_RETENTION_MIRROR_COUNT", "2")
    monkeypatch.setenv("LOCAL_CORE_BACKUP_BASE_INTERVAL_HOURS", "72")
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: True)
    monkeypatch.setattr(
        incremental,
        "postgres_status",
        lambda: {"archive_mode": "on", "wal_ready_count": 0, "wal_bytes": 1024},
    )

    plan = incremental.build_plan(_args(require_mirror=True))

    assert plan["can_run"] is True
    assert plan["policy"]["mode"] == "incremental_runtime_backup"
    assert plan["policy"]["primary_root"] == str(primary)
    assert plan["policy"]["mirror_root"] == str(mirror)
    assert plan["policy"]["retention_local_count"] == 5
    assert plan["policy"]["retention_mirror_count"] == 2
    assert plan["policy"]["require_mirror"] is True
    assert plan["policy"]["base_interval_hours"] == 72
    assert plan["policy"]["mirror_scopes"] == ["postgres_chain", "runtime_metadata", "auth_state"]
    assert plan["base_backup_required"] is True


def test_policy_blocks_when_required_mirror_is_missing(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(primary / "postgres-wal-archive"))
    monkeypatch.delenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: True)
    monkeypatch.setattr(
        incremental,
        "postgres_status",
        lambda: {"archive_mode": "on", "wal_ready_count": 0, "wal_bytes": 1024},
    )

    plan = incremental.build_plan(_args(require_mirror="true"))

    assert plan["can_run"] is False
    assert "mirror_required_but_not_configured" in plan["blocking_reasons"]


def test_prune_incremental_removes_oldest_snapshot_and_unprotected_base(monkeypatch, tmp_path):
    root = tmp_path / "backups"
    wal_root = root / "postgres-wal-archive"
    base_root = wal_root / "base_backups"
    root.mkdir()
    base_root.mkdir(parents=True)
    dates = [
        ("old", "2026-05-18T00:00:00Z", "base_old"),
        ("middle", "2026-05-19T00:00:00Z", "base_middle"),
        ("new", "2026-05-20T00:00:00Z", "base_new"),
    ]
    for name, created_at, base_id in dates:
        backup_dir = root / name
        backup_dir.mkdir()
        (base_root / base_id).mkdir()
        (backup_dir / "manifest.json").write_text(
            (
                '{"mode": "incremental_runtime_backup", "created_at": "%s", '
                '"components": {"postgres": {"base_backup_id": "%s"}}}\n'
            )
            % (created_at, base_id),
            encoding="utf-8",
        )

    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    removed = incremental.prune_incremental(root, keep_count=2, protected=root / "new")

    assert removed["snapshots"] == [str(root / "old")]
    assert removed["base_backups"] == [str(base_root / "base_old")]
    assert not (root / "old").exists()
    assert not (base_root / "base_old").exists()
    assert (root / "middle").exists()
    assert (root / "new").exists()
    assert (base_root / "base_middle").exists()


def test_mirror_incremental_artifacts_skips_legacy_backups_and_rewrites_manifest(tmp_path):
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
