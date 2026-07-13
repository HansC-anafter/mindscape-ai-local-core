from __future__ import annotations

import json
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.backup import (
    EXACT_BACKUP_OPTIONS,
    REQUIRED_DATABASE_ARTIFACTS,
    BackupGate,
)
from remote_workbench_authorization_cutover.io import CutoverError


NOW = datetime(2026, 7, 13, 6, 0, tzinfo=timezone.utc)


def _manifest(repo_root: Path, *, age_seconds: int = 30) -> dict:
    return {
        "schema_version": "1.0",
        "repo_root": str(repo_root),
        "created_at": (NOW - timedelta(seconds=age_seconds)).isoformat(),
        "options": dict(EXACT_BACKUP_OPTIONS),
        "artifacts": [
            {"path": path, "bytes": 1, "sha256": "a" * 64}
            for path in sorted(REQUIRED_DATABASE_ARTIFACTS)
        ],
    }


def _write_backup(path: Path, manifest: dict) -> None:
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    for relative in REQUIRED_DATABASE_ARTIFACTS:
        artifact = path / relative
        artifact.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        current = artifact.parent
        while current != path:
            current.chmod(0o700)
            current = current.parent
        artifact.write_bytes(b"x")
        artifact.chmod(0o600)
    manifest_path = path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_path.chmod(0o600)


class BackupExecutor:
    def __init__(self, repo_root: Path, manifest: dict) -> None:
        self.repo_root = repo_root
        self.manifest = manifest
        self.calls: list[tuple[list[str], float]] = []

    def run(self, args, *, timeout_seconds=60.0, input_text=None) -> str:
        command = list(args)
        self.calls.append((command, timeout_seconds))
        if any(item.endswith("backup_local_runtime.sh") for item in command):
            output = Path(command[command.index("--output-dir") + 1])
            name = command[command.index("--name") + 1]
            _write_backup(output / name, self.manifest)
            return ""
        if command[0].endswith("verify_local_runtime_backup.sh"):
            return ""
        if command[:3] == ["docker", "exec", "mindscape-ai-local-core-postgres"]:
            return NOW.isoformat().replace("+00:00", "Z")
        raise AssertionError(command)


def _verify_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict,
) -> Path:
    backup = tmp_path / "backup"
    _write_backup(backup, manifest)
    executor = BackupExecutor(REPO_ROOT, manifest)
    result = BackupGate(repo_root=REPO_ROOT, executor=executor)._verify(backup)
    assert executor.calls[0] == (
        [str(REPO_ROOT / "scripts/verify_local_runtime_backup.sh"), str(backup)],
        300.0,
    )
    return result


def test_backup_gate_accepts_only_fresh_exact_current_database_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _verify_existing(tmp_path, monkeypatch, _manifest(REPO_ROOT)) == tmp_path / "backup"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(repo_root="/tmp/other"), "canonical Local"),
        (lambda value: value["options"].update(skip_db=True), "exact DB-only"),
        (lambda value: value["options"].update(skip_files=False), "exact DB-only"),
        (lambda value: value["artifacts"].pop(), "both current PostgreSQL"),
        (lambda value: value.update(schema_version="2.0"), "legacy backup schema"),
        (
            lambda value: value.update(
                created_at=(NOW - timedelta(seconds=901)).isoformat()
            ),
            "fresh current-database",
        ),
    ],
)
def test_backup_gate_rejects_generic_old_or_incomplete_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    message: str,
) -> None:
    manifest = _manifest(REPO_ROOT)
    mutation(manifest)
    with pytest.raises(CutoverError, match=message):
        _verify_existing(tmp_path, monkeypatch, manifest)


def test_backup_gate_creates_with_canonical_db_only_script_and_bounded_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    monkeypatch.delenv("REMOTE_WORKBENCH_VERIFIED_BACKUP_DIR", raising=False)
    monkeypatch.setenv("REMOTE_WORKBENCH_BACKUP_OUTPUT_DIR", str(output))
    manifest = _manifest(REPO_ROOT)
    executor = BackupExecutor(REPO_ROOT, manifest)

    result = BackupGate(repo_root=REPO_ROOT, executor=executor).verify_or_create()

    create, verify, _clock = executor.calls
    assert create[0][:5] == [
        "/bin/bash",
        "-c",
        'umask 077; exec "$@"',
        "phase06-backup",
        str(REPO_ROOT / "scripts/backup_local_runtime.sh"),
    ]
    assert create[0][-1] == "--skip-files"
    assert create[1] == 1800.0
    assert verify[0] == [
        str(REPO_ROOT / "scripts/verify_local_runtime_backup.sh"),
        str(result),
    ]
    assert verify[1] == 300.0


def test_legacy_verified_backup_environment_cannot_bypass_fresh_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = tmp_path / "stale"
    _write_backup(stale, _manifest(REPO_ROOT, age_seconds=901))
    output = tmp_path / "fresh"
    output.mkdir(mode=0o700)
    monkeypatch.setenv("REMOTE_WORKBENCH_VERIFIED_BACKUP_DIR", str(stale))
    monkeypatch.setenv("REMOTE_WORKBENCH_BACKUP_OUTPUT_DIR", str(output))
    executor = BackupExecutor(REPO_ROOT, _manifest(REPO_ROOT))

    result = BackupGate(repo_root=REPO_ROOT, executor=executor).verify_or_create()

    assert result.parent == output
    assert result != stale
    assert str(REPO_ROOT / "scripts/backup_local_runtime.sh") in executor.calls[0][0]


def test_backup_gate_rejects_world_readable_output_root_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    output.chmod(0o755)
    monkeypatch.setenv("REMOTE_WORKBENCH_BACKUP_OUTPUT_DIR", str(output))
    executor = BackupExecutor(REPO_ROOT, _manifest(REPO_ROOT))

    with pytest.raises(CutoverError, match="mode must be 0700"):
        BackupGate(repo_root=REPO_ROOT, executor=executor).verify_or_create()

    assert executor.calls == []


@pytest.mark.parametrize("relative", ["manifest.json", "postgres/mindscape_core.dump"])
def test_backup_gate_rejects_world_readable_sensitive_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    backup = tmp_path / "backup"
    _write_backup(backup, _manifest(REPO_ROOT))
    (backup / relative).chmod(0o644)
    executor = BackupExecutor(REPO_ROOT, _manifest(REPO_ROOT))

    with pytest.raises(CutoverError, match="file mode must be 0600"):
        BackupGate(repo_root=REPO_ROOT, executor=executor)._verify(backup)

    assert executor.calls == []


def test_backup_gate_rejects_symlinked_database_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = tmp_path / "backup"
    _write_backup(backup, _manifest(REPO_ROOT))
    artifact = backup / "postgres/mindscape_core.dump"
    artifact.unlink()
    artifact.symlink_to(backup / "manifest.json")
    executor = BackupExecutor(REPO_ROOT, _manifest(REPO_ROOT))

    with pytest.raises(CutoverError, match="symbolic links"):
        BackupGate(repo_root=REPO_ROOT, executor=executor)._verify(backup)

    assert executor.calls == []


def test_backup_gate_rejects_non_current_user_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    class Metadata:
        st_uid = os.getuid() + 1
        st_mode = stat.S_IFDIR | 0o700

    monkeypatch.setattr(Path, "stat", lambda self: Metadata())
    from remote_workbench_authorization_cutover.backup_privacy import (
        resolve_private_output_directory,
    )

    with pytest.raises(CutoverError, match="owned by the current user"):
        resolve_private_output_directory("/private/tmp")
