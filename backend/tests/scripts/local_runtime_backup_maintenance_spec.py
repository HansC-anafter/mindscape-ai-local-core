import importlib.util
from argparse import Namespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = _load(
    "local_runtime_backup_policy_maintenance",
    REPO_ROOT / "scripts" / "local_runtime_backup_policy.py",
)


def _args(root: Path, backup_dir: Path) -> Namespace:
    return Namespace(
        backup_dir=str(backup_dir),
        output_dir=str(root),
        mirror_root="",
        retention_local_count=1,
        retention_mirror_count=1,
        min_free_gb=1,
        require_mirror=False,
        base_interval_hours=168,
        mirror_scopes="postgres_chain",
        postgres_only=False,
    )


def test_verify_prune_refuses_mutation_when_verification_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backup_dir = tmp_path / "backups" / "latest"
    backup_dir.mkdir(parents=True)
    (backup_dir / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        policy,
        "build_config",
        lambda _args: {
            "primary_root": backup_dir.parent,
            "wal_archive_root": tmp_path / "wal",
            "retention_local_count": 1,
        },
    )
    monkeypatch.setattr(
        policy,
        "verify_incremental_dir",
        lambda _path: {"success": False},
    )
    monkeypatch.setattr(
        policy,
        "prune_incremental",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("prune must not run")
        ),
    )

    try:
        policy.verify_and_prune(_args(backup_dir.parent, backup_dir))
    except SystemExit as exc:
        assert "verification failed" in str(exc)
    else:
        raise AssertionError("verification failure must stop maintenance")


def test_verify_prune_emits_before_after_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backup_dir = tmp_path / "backups" / "latest"
    wal_root = tmp_path / "wal"
    backup_dir.mkdir(parents=True)
    wal_root.mkdir()
    (backup_dir / "manifest.json").write_text("{}", encoding="utf-8")
    segment_snapshots = iter([["0001", "0002"], ["0002"]])
    byte_snapshots = iter([32, 16])
    monkeypatch.setattr(
        policy,
        "build_config",
        lambda _args: {
            "primary_root": backup_dir.parent,
            "wal_archive_root": wal_root,
            "retention_local_count": 1,
        },
    )
    monkeypatch.setattr(
        policy,
        "verify_incremental_dir",
        lambda _path: {"success": True},
    )
    monkeypatch.setattr(
        policy,
        "list_wal_segments",
        lambda _path: next(segment_snapshots),
    )
    monkeypatch.setattr(
        policy,
        "dir_size_bytes",
        lambda _path: next(byte_snapshots),
    )
    monkeypatch.setattr(
        policy,
        "prune_incremental",
        lambda *_args, **_kwargs: {
            "snapshots": [],
            "base_backups": [],
            "wal_segments": ["0001"],
            "warnings": [],
        },
    )

    result = policy.verify_and_prune(_args(backup_dir.parent, backup_dir))

    assert result["success"] is True
    assert result["before"] == {
        "wal_segment_count": 2,
        "wal_archive_bytes": 32,
    }
    assert result["after"] == {
        "wal_segment_count": 1,
        "wal_archive_bytes": 16,
    }
    assert result["pruned"]["wal_segments"] == ["0001"]
