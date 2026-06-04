import importlib.util
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


job = _load_module(
    "local_runtime_backup_job",
    REPO_ROOT / "scripts" / "local_runtime_backup_job.py",
)


def test_latest_backup_reads_host_backup_root(tmp_path):
    root = tmp_path / "backups"
    root.mkdir()
    older = root / "older"
    newer = root / "newer"
    older.mkdir()
    newer.mkdir()
    for backup_dir, created_at, size in [
        (older, "2026-05-19T00:00:00Z", 11),
        (newer, "2026-05-20T00:00:00Z", 17),
    ]:
        (backup_dir / "artifact.bin").write_bytes(b"x" * size)
        (backup_dir / "manifest.json").write_text(
            """
{
  "backup_name": "%s",
  "created_at": "%s",
  "artifacts": [
    {"path": "artifact.bin", "bytes": %s, "sha256": "unused"}
  ]
}
"""
            % (backup_dir.name, created_at, size),
            encoding="utf-8",
        )

    latest = job.command_latest_backup(Namespace(output_dir=str(root)))

    assert latest["backup_root"] == str(root)
    assert latest["latest_backup"]["backup_name"] == "newer"
    assert latest["latest_backup"]["host_backup_dir"] == str(newer)
    assert latest["latest_backup"]["total_bytes"] == 17


def test_policy_flags_use_single_configurable_path():
    args = Namespace(
        output_dir="/primary",
        mirror_root="/mirror",
        retention_local_count=7,
        retention_mirror_count=3,
        min_free_gb=20,
        require_mirror=True,
        base_interval_hours=168,
        mirror_scopes="postgres_chain,runtime_metadata,auth_state",
    )

    cmd = job.add_policy_flags(["python3", "scripts/local_runtime_backup_policy.py", "plan"], args)

    assert cmd == [
        "python3",
        "scripts/local_runtime_backup_policy.py",
        "plan",
        "--output-dir",
        "/primary",
        "--mirror-root",
        "/mirror",
        "--retention-local-count",
        "7",
        "--retention-mirror-count",
        "3",
        "--min-free-gb",
        "20",
        "--require-mirror",
        "true",
        "--base-interval-hours",
        "168",
        "--mirror-scopes",
        "postgres_chain,runtime_metadata,auth_state",
    ]


def test_latest_backup_reads_incremental_manifest_components(tmp_path):
    root = tmp_path / "backups"
    backup_dir = root / "incremental"
    backup_dir.mkdir(parents=True)
    (backup_dir / "manifest.json").write_text(
        """
{
  "schema_version": "2.0",
  "mode": "incremental_runtime_backup",
  "backup_name": "incremental",
  "created_at": "2026-05-20T00:00:00Z",
  "total_bytes": 123,
  "components": {
    "postgres": {"base_backup_id": "base_20260520T000000Z"},
    "files": {"snapshot_relpath": "app-data"}
  }
}
""",
        encoding="utf-8",
    )

    latest = job.command_latest_backup(Namespace(output_dir=str(root)))

    assert latest["latest_backup"]["mode"] == "incremental_runtime_backup"
    assert latest["latest_backup"]["artifact_count"] == 2
    assert latest["latest_backup"]["total_bytes"] == 123
    assert latest["latest_backup"]["base_backup_id"] == "base_20260520T000000Z"
    assert latest["latest_backup"]["file_snapshot_id"] == "incremental"


def test_google_drive_status_detects_my_drive_mount(tmp_path, monkeypatch):
    cloud_root = tmp_path / "CloudStorage"
    my_drive = cloud_root / "GoogleDrive-hans@anafter.co" / "我的雲端硬碟"
    my_drive.mkdir(parents=True)
    monkeypatch.setenv("GOOGLE_DRIVE_CLOUDSTORAGE_ROOT", str(cloud_root))

    status = job.command_google_drive_status(Namespace())

    assert status["available"] is True
    assert status["account_label"] == "hans@anafter.co"
    assert status["my_drive_path"] == str(my_drive)
    assert status["recommended_mirror_root"] == str(my_drive / "Mindscape" / "local-core-runtime-backups")
    assert status["recommended_resource_root"] == str(my_drive / "Mindscape" / "local-core-resource-collaboration")
    assert status["recommended_mirror_scopes"] == ["postgres_chain", "runtime_metadata", "auth_state"]


def test_prepare_google_drive_creates_collaboration_policy(tmp_path, monkeypatch):
    cloud_root = tmp_path / "CloudStorage"
    my_drive = cloud_root / "GoogleDrive-hans@anafter.co" / "My Drive"
    my_drive.mkdir(parents=True)
    monkeypatch.setenv("GOOGLE_DRIVE_CLOUDSTORAGE_ROOT", str(cloud_root))

    mirror_root = my_drive / "Mindscape" / "local-core-runtime-backups"
    resource_root = my_drive / "Mindscape" / "local-core-resource-collaboration"
    result = job.command_prepare_google_drive(
        Namespace(mirror_root=str(mirror_root), resource_root=str(resource_root))
    )

    assert result["success"] is True
    assert result["prepared"] is True
    assert mirror_root.is_dir()
    assert (resource_root / "incoming").is_dir()
    assert (resource_root / "outgoing").is_dir()
    assert (resource_root / "resource-index").is_dir()
    assert (resource_root / ".mindscape-sync-policy.json").is_file()
