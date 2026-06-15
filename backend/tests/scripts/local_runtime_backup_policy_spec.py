import importlib.util
import json
import subprocess
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


def _postgres_ok():
    return {
        "archive_mode": "on",
        "archive_command": "/usr/local/bin/mindscape-archive-wal %p %f /archive",
        "wal_ready_count": 0,
        "wal_bytes": 1024,
        "archiver_archived_count": 1,
        "archiver_last_archived_wal": "000000010000000000000001",
        "archiver_last_archived_time": "2026-05-25T00:00:00+00:00",
        "archiver_failed_count": 0,
        "archiver_last_failed_wal": "",
        "archiver_last_failed_time": "",
        "archiver_stats_reset": "2026-05-25T00:00:00+00:00",
    }


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
        _postgres_ok,
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
        _postgres_ok,
    )

    plan = incremental.build_plan(_args(require_mirror="true"))

    assert plan["can_run"] is False
    assert "mirror_required_but_not_configured" in plan["blocking_reasons"]


def test_policy_blocks_current_archiver_failure(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    wal_root = primary / "postgres-wal-archive"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_REQUIRE_MIRROR", "false")
    monkeypatch.delenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: True)

    def _postgres_failing():
        state = _postgres_ok()
        state.update(
            {
                "archiver_failed_count": 1,
                "archiver_last_failed_wal": "000000010000000000000002",
                "archiver_last_failed_time": "2026-05-25T00:05:00+00:00",
            }
        )
        return state

    monkeypatch.setattr(incremental, "postgres_status", _postgres_failing)

    plan = incremental.build_plan(_args())

    assert plan["can_run"] is False
    assert "postgres_archiver_currently_failing" in plan["blocking_reasons"]


def test_policy_blocks_wal_archive_segment_size_mismatch(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    wal_root = primary / "postgres-wal-archive"
    wal_root.mkdir(parents=True)
    (wal_root / "000000010000000000000001").write_bytes(b"partial wal")
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_REQUIRE_MIRROR", "false")
    monkeypatch.delenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: True)
    monkeypatch.setattr(incremental, "postgres_status", _postgres_ok)

    plan = incremental.build_plan(_args())

    assert plan["can_run"] is False
    assert "wal_archive_segment_size_mismatch" in plan["blocking_reasons"]
    assert plan["wal_segment_size_mismatches"] == [
        {
            "name": "000000010000000000000001",
            "bytes": len(b"partial wal"),
            "expected_bytes": incremental.WAL_SEGMENT_BYTES,
        }
    ]


def test_policy_accepts_valid_wal_archive_segment(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    wal_root = primary / "postgres-wal-archive"
    wal_root.mkdir(parents=True)
    (wal_root / "000000010000000000000001").write_bytes(
        b"\0" * incremental.WAL_SEGMENT_BYTES
    )
    monkeypatch.setenv("LOCAL_CORE_BACKUP_ROOT", str(primary))
    monkeypatch.setenv("LOCAL_CORE_POSTGRES_WAL_ARCHIVE_HOST_DIR", str(wal_root))
    monkeypatch.setenv("LOCAL_CORE_BACKUP_REQUIRE_MIRROR", "false")
    monkeypatch.delenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", raising=False)
    monkeypatch.setattr(incremental, "disk_free_bytes", lambda _path: 80 * incremental.BYTES_PER_GB)
    monkeypatch.setattr(incremental, "command_exists", lambda _name: True)
    monkeypatch.setattr(incremental, "postgres_status", _postgres_ok)

    plan = incremental.build_plan(_args())

    assert plan["can_run"] is True
    assert plan["wal_segment_size_mismatches"] == []


def test_empty_cli_mirror_root_disables_env_mirror(monkeypatch, tmp_path):
    mirror = tmp_path / "env-mirror"
    monkeypatch.setenv("LOCAL_CORE_BACKUP_MIRROR_ROOT", str(mirror))

    assert incremental.resolve_mirror_root("") is None


def test_estimate_temp_parent_uses_backup_root_for_previous_snapshot(tmp_path):
    source = tmp_path / "runtime" / "data"
    previous = tmp_path / "primary" / "incremental_20260520T000000Z" / "app-data"
    source.mkdir(parents=True)
    previous.mkdir(parents=True)

    temp_parent = incremental.estimate_temp_parent(source, previous)

    assert temp_parent == tmp_path / "primary"


def test_estimate_temp_parent_uses_source_parent_without_previous_snapshot(tmp_path):
    source = tmp_path / "runtime" / "data"
    source.mkdir(parents=True)

    temp_parent = incremental.estimate_temp_parent(source, None)

    assert temp_parent == tmp_path / "runtime"


def test_estimate_snapshot_transfer_falls_back_when_link_dest_is_unusable(monkeypatch, tmp_path):
    source = tmp_path / "runtime" / "data"
    previous = tmp_path / "primary" / "old" / "app-data"
    source.mkdir(parents=True)
    previous.mkdir(parents=True)
    calls = []
    monkeypatch.setenv("LOCAL_CORE_BACKUP_RSYNC_DRY_RUN_ESTIMATE", "true")

    def fake_run_capture(cmd, timeout=None):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 11, "", "link-dest failed")
        return subprocess.CompletedProcess(cmd, 0, "Total transferred file size: 42 B\n", "")

    monkeypatch.setattr(incremental, "run_capture", fake_run_capture)

    assert incremental.estimate_snapshot_transfer_bytes(source, previous, 30) == 42
    assert any(str(previous) in part for part in calls[0])
    assert not any(str(previous) in part for part in calls[1])


def test_estimate_snapshot_transfer_uses_source_size_for_transient_rsync_race(monkeypatch, tmp_path):
    source = tmp_path / "runtime" / "data"
    (source / "runtime").mkdir(parents=True)
    (source / "runtime" / "state.json").write_bytes(b"runtime")
    (source / "postgres").mkdir()
    (source / "postgres" / "PG_VERSION").write_bytes(b"postgres")
    (source / "backups").mkdir()
    (source / "backups" / "old.bin").write_bytes(b"backup")
    (source / "ig_thumbnails").mkdir()
    (source / "ig_thumbnails" / "cache.png").write_bytes(b"cache")

    def fake_run_capture(cmd, timeout=None):
        return subprocess.CompletedProcess(cmd, 23, "", "vanished file")

    monkeypatch.setenv("LOCAL_CORE_BACKUP_RSYNC_DRY_RUN_ESTIMATE", "true")
    monkeypatch.setattr(incremental, "run_capture", fake_run_capture)
    monkeypatch.setattr(
        incremental,
        "disk_usage_many_bytes",
        lambda paths: sum(incremental.dir_size_bytes(path) for path in paths),
    )

    assert incremental.estimate_snapshot_transfer_bytes(source, None, 30) == len(b"runtime")


def test_estimate_snapshot_transfer_uses_du_by_default(monkeypatch, tmp_path):
    source = tmp_path / "runtime" / "data"
    (source / "runtime").mkdir(parents=True)
    (source / "runtime" / "state.json").write_bytes(b"runtime")
    (source / "backups").mkdir()
    (source / "backups" / "old.bin").write_bytes(b"backup")
    (source / "ig_debug_scroll_20260613.png").write_bytes(b"debug")
    (source / "ig_visit_timeout_handle_20260613.png").write_bytes(b"timeout")
    monkeypatch.setattr(
        incremental,
        "disk_usage_many_bytes",
        lambda paths: sum(incremental.dir_size_bytes(path) for path in paths),
    )

    def fail_run_capture(cmd, timeout=None):
        raise AssertionError("rsync dry-run should be disabled by default")

    monkeypatch.setattr(incremental, "run_capture", fail_run_capture)

    assert incremental.estimate_snapshot_transfer_bytes(source, None, 30) == len(b"runtime")


def test_estimate_mirror_snapshot_transfer_uses_scoped_size_for_transient_rsync_race(monkeypatch, tmp_path):
    source = tmp_path / "runtime" / "data"
    (source / "runtime").mkdir(parents=True)
    (source / "runtime" / "state.json").write_bytes(b"runtime")
    (source / "uploads").mkdir()
    (source / "uploads" / "blob.bin").write_bytes(b"blob")

    def fake_run_capture(cmd, timeout=None):
        return subprocess.CompletedProcess(cmd, 24, "", "vanished file")

    monkeypatch.setenv("LOCAL_CORE_BACKUP_RSYNC_DRY_RUN_ESTIMATE", "true")
    monkeypatch.setattr(incremental, "run_capture", fake_run_capture)
    monkeypatch.setattr(
        incremental,
        "disk_usage_many_bytes",
        lambda paths: sum(incremental.dir_size_bytes(path) for path in paths),
    )

    assert (
        incremental.estimate_mirror_snapshot_transfer_bytes(source, None, ["runtime_metadata"], 30)
        == len(b"runtime")
    )


def test_run_pg_basebackup_uses_fast_checkpoint(monkeypatch, tmp_path):
    wal_root = tmp_path / "postgres-wal-archive"
    captured = {}

    def fake_run_text(cmd, timeout=None):
        captured["cmd"] = cmd
        return ""

    monkeypatch.setattr(incremental, "run_text", fake_run_text)

    manifest = incremental.run_pg_basebackup("base_20260613T000000Z", wal_root, 30)

    assert "-c fast" in captured["cmd"][-1]
    assert manifest["base_backup_id"] == "base_20260613T000000Z"


def test_rsync_snapshot_falls_back_to_full_snapshot_when_link_dest_fails(monkeypatch, tmp_path):
    source = tmp_path / "runtime" / "data"
    previous = tmp_path / "primary" / "old" / "app-data"
    target = tmp_path / "primary" / "new" / "app-data"
    source.mkdir(parents=True)
    previous.mkdir(parents=True)
    calls = []

    def fake_run_capture(cmd, timeout=None):
        calls.append(cmd)
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 11, "", "link-dest failed")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(incremental, "run_capture", fake_run_capture)

    results = incremental.rsync_snapshot(source, target, previous, 30)

    assert any(str(previous) in part for part in calls[0])
    assert not any(str(previous) in part for part in calls[1])
    assert results[-1]["warning"] == "link_dest_failed_fell_back_to_full_snapshot"


def test_rsync_snapshot_returns_after_first_success(monkeypatch, tmp_path):
    source = tmp_path / "runtime" / "data"
    previous = tmp_path / "primary" / "old" / "app-data"
    target = tmp_path / "primary" / "new" / "app-data"
    source.mkdir(parents=True)
    previous.mkdir(parents=True)
    calls = []

    def fake_run_capture(cmd, timeout=None):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(incremental, "run_capture", fake_run_capture)

    results = incremental.rsync_snapshot(source, target, previous, 30)

    assert len(calls) == 1
    assert len(results) == 1
    assert results[0]["returncode"] == 0


def test_rsync_snapshot_command_uses_link_dest_without_source_hardlink_scan(tmp_path):
    source = tmp_path / "runtime" / "data"
    previous = tmp_path / "primary" / "old" / "app-data"
    target = tmp_path / "primary" / "new" / "app-data"
    source.mkdir(parents=True)
    previous.mkdir(parents=True)

    cmd = incremental.rsync_snapshot_command(source, target, previous)

    assert "-a" in cmd
    assert "-aH" not in cmd
    assert f"--link-dest={previous}" in cmd


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


def test_prune_incremental_removes_wal_before_earliest_retained_base_start(tmp_path):
    root = tmp_path / "backups"
    wal_root = root / "postgres-wal-archive"
    base_root = wal_root / "base_backups"
    root.mkdir()
    base_root.mkdir(parents=True)
    dates = [
        ("old", "2026-05-18T00:00:00Z", "base_old", "000000010000000000000001"),
        ("new", "2026-05-20T00:00:00Z", "base_new", "000000010000000000000003"),
    ]
    for name, created_at, base_id, start_wal in dates:
        backup_dir = root / name
        backup_dir.mkdir()
        base_dir = base_root / base_id
        base_dir.mkdir()
        (base_dir / "backup_label").write_text(
            f"START WAL LOCATION: 0/0 (file {start_wal})\n",
            encoding="utf-8",
        )
        (backup_dir / "manifest.json").write_text(
            (
                '{"mode": "incremental_runtime_backup", "created_at": "%s", '
                '"components": {"postgres": {"base_backup_id": "%s"}}}\n'
            )
            % (created_at, base_id),
            encoding="utf-8",
        )
    for wal_name in [
        "000000010000000000000001",
        "000000010000000000000002",
        "000000010000000000000003",
        "000000010000000000000004",
    ]:
        (wal_root / wal_name).write_bytes(b"\0" * incremental.WAL_SEGMENT_BYTES)

    removed = incremental.prune_incremental(root, keep_count=1, protected=root / "new", wal_root=wal_root)

    assert removed["snapshots"] == [str(root / "old")]
    assert removed["base_backups"] == [str(base_root / "base_old")]
    assert removed["wal_segments"] == [
        str(wal_root / "000000010000000000000001"),
        str(wal_root / "000000010000000000000002"),
    ]
    assert not (wal_root / "000000010000000000000001").exists()
    assert not (wal_root / "000000010000000000000002").exists()
    assert (wal_root / "000000010000000000000003").is_file()
    assert (wal_root / "000000010000000000000004").is_file()


def test_verify_incremental_allows_pruned_wal_before_base_start(tmp_path):
    backup_dir = tmp_path / "backup"
    wal_root = tmp_path / "postgres-wal-archive"
    base_dir = wal_root / "base_backups" / "base_new"
    retained_segment = "000000010000000000000003"

    (backup_dir / "app-data").mkdir(parents=True)
    base_dir.mkdir(parents=True)
    wal_root.mkdir(exist_ok=True)
    (base_dir / "PG_VERSION").write_text("16\n", encoding="utf-8")
    (wal_root / retained_segment).write_bytes(b"\0" * incremental.WAL_SEGMENT_BYTES)
    incremental.write_json(
        backup_dir / "manifest.json",
        {
            "mode": "incremental_runtime_backup",
            "components": {
                "files": {"snapshot_relpath": "app-data"},
                "postgres": {
                    "base_backup_dir": str(base_dir),
                    "base_backup_start_wal_segment": retained_segment,
                    "wal_archive_dir": str(wal_root),
                    "wal_segments": [
                        "000000010000000000000001",
                        "000000010000000000000002",
                        retained_segment,
                    ],
                },
            },
        },
    )

    result = incremental.verify_incremental_dir(backup_dir)

    assert result["success"] is True


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
