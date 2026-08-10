import json
from pathlib import Path

import pytest

from scripts.postgres_disposable_restore_core.commands import (
    _compose,
    _critical_database_evidence,
    _environment,
    _readiness_query,
    _require_restore_service_running,
)
from scripts.postgres_disposable_restore_core.policy import (
    RestoreScope,
    validate_restore_scope,
)
from scripts.postgres_disposable_restore_core.receipt import (
    read_restore_receipt,
    write_restore_receipt,
)


def _restore_source(tmp_path: Path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    backup = tmp_path / "backups" / "snapshot-1"
    wal = backup.parent / "postgres-wal-archive"
    base = wal / "base_backups" / "base-1"
    base.mkdir(parents=True)
    (base / "PG_VERSION").write_text("16\n", encoding="utf-8")
    (base / "backup_label").write_text(
        "START WAL LOCATION: 0/1000000 (file 000000010000000000000001)\n",
        encoding="utf-8",
    )
    segment = "000000010000000000000001"
    (wal / segment).write_bytes(b"wal")
    backup.mkdir(parents=True)
    (backup / "manifest.json").write_text(
        json.dumps(
            {
                "mode": "incremental_runtime_backup",
                "created_at": "2026-07-16T12:00:00Z",
                "components": {
                    "postgres": {
                        "base_backup_id": "base-1",
                        "base_backup_dir": "/relocated/missing/base-1",
                        "wal_archive_dir": "/relocated/missing/wal",
                        "wal_segments": [segment],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return validate_restore_scope(
        RestoreScope(
            project="mindscape-runtime-restore-drill",
            compose_file=compose,
            backup_dir=backup,
            receipt_dir=tmp_path / "receipts",
        )
    )


def test_restore_scope_resolves_relocated_incremental_chain(tmp_path: Path):
    source = _restore_source(tmp_path)

    assert source.base_dir.name == "base-1"
    assert source.wal_dir.name == "postgres-wal-archive"
    assert source.recovery_target_time == "2026-07-16 12:00:00+00:00"
    assert source.required_wal_segments == ("000000010000000000000001",)


def test_restore_scope_rejects_non_disposable_project(tmp_path: Path):
    source = _restore_source(tmp_path)

    with pytest.raises(ValueError, match="restore_project_label_required"):
        validate_restore_scope(
            RestoreScope(
                project="mindscape-runtime",
                compose_file=source.scope.compose_file,
                backup_dir=source.scope.backup_dir,
                receipt_dir=source.scope.receipt_dir,
            )
        )


def test_restore_scope_rejects_existing_wal_path_outside_backup_root(
    tmp_path: Path,
):
    source = _restore_source(tmp_path)
    manifest_path = source.scope.backup_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    outside_wal = tmp_path / "outside-wal"
    outside_base = outside_wal / "base_backups" / "base-1"
    outside_base.mkdir(parents=True)
    (outside_base / "PG_VERSION").write_text("16\n", encoding="utf-8")
    (outside_base / "backup_label").write_text("label\n", encoding="utf-8")
    segment = "000000010000000000000001"
    (outside_wal / segment).write_bytes(b"wal")
    manifest["components"]["postgres"]["wal_archive_dir"] = str(outside_wal)
    manifest["components"]["postgres"]["base_backup_dir"] = str(outside_base)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="restore_wal_directory_outside_backup_root",
    ):
        validate_restore_scope(source.scope)


def test_restore_scope_accepts_project_named_system_temp_bind_dir(
    tmp_path: Path,
):
    source = _restore_source(tmp_path)
    project = "mindscape-runtime-bind-restore-drill"
    data_dir = tmp_path / project

    validated = validate_restore_scope(
        RestoreScope(
            project=project,
            compose_file=source.scope.compose_file,
            backup_dir=source.scope.backup_dir,
            receipt_dir=source.scope.receipt_dir,
            data_dir=data_dir,
        )
    )

    assert validated.scope.data_dir == data_dir.resolve()
    assert _environment(validated)["MINDSCAPE_RECOVERY_RESTORE_DATA_DIR"] == str(
        data_dir.resolve()
    )


def test_restore_scope_rejects_unscoped_bind_directory(tmp_path: Path):
    source = _restore_source(tmp_path)

    with pytest.raises(
        ValueError,
        match="restore_data_directory_must_match_project",
    ):
        validate_restore_scope(
            RestoreScope(
                project="mindscape-runtime-bind-restore-drill",
                compose_file=source.scope.compose_file,
                backup_dir=source.scope.backup_dir,
                receipt_dir=source.scope.receipt_dir,
                data_dir=tmp_path / "other-project",
            )
        )


def test_restore_scope_allows_exact_nonempty_bind_only_for_cleanup(
    tmp_path: Path,
):
    source = _restore_source(tmp_path)
    project = "mindscape-runtime-cleanup-restore-drill"
    data_dir = tmp_path / project
    data_dir.mkdir()
    (data_dir / "PG_VERSION").write_text("16\n", encoding="utf-8")
    scope = RestoreScope(
        project=project,
        compose_file=source.scope.compose_file,
        backup_dir=source.scope.backup_dir,
        receipt_dir=source.scope.receipt_dir,
        data_dir=data_dir,
    )

    with pytest.raises(
        ValueError,
        match="restore_data_directory_not_empty_cleanup_first",
    ):
        validate_restore_scope(scope)
    validated = validate_restore_scope(scope, allow_existing_data=True)

    assert validated.scope.data_dir == data_dir.resolve()


def test_restore_environment_ignores_unscoped_data_dir_injection(
    monkeypatch,
    tmp_path: Path,
):
    source = _restore_source(tmp_path)
    monkeypatch.setenv(
        "MINDSCAPE_RECOVERY_RESTORE_DATA_DIR",
        "/var/lib/postgresql/data",
    )

    assert "MINDSCAPE_RECOVERY_RESTORE_DATA_DIR" not in _environment(source)


def test_restore_compose_uses_disposable_restore_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _restore_source(tmp_path)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs) -> __import__("subprocess").CompletedProcess[str]:
        calls.append(cmd)
        return __import__("subprocess").CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='{"services": {}}',
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.postgres_disposable_restore_core.commands.subprocess.run",
        fake_run,
    )

    _compose(source, "ps", "--format", "json")

    assert calls
    command = calls[0]
    assert "--profile" in command
    assert command[command.index("--profile") + 1] == "postgres-disposable-restore"
    assert "postgres-recovery-drill" not in command


def test_readiness_timeout_is_not_a_terminal_restore_exception(
    monkeypatch,
    tmp_path: Path,
):
    source = _restore_source(tmp_path)

    def timeout(*_args, **_kwargs):
        raise __import__("subprocess").TimeoutExpired("docker compose exec", 10)

    monkeypatch.setattr(
        "scripts.postgres_disposable_restore_core.commands._query",
        timeout,
    )

    result = _readiness_query(source)

    assert result.returncode == 124
    assert result.stderr == "restore_readiness_probe_timeout"


def test_exited_restore_service_fails_before_global_timeout() -> None:
    completed = __import__("subprocess").CompletedProcess(
        args=("docker", "compose", "exec"),
        returncode=1,
        stdout="",
        stderr='service "postgres-recovery-restore" is not running',
    )

    with pytest.raises(
        RuntimeError,
        match="restore_service_exited_before_ready",
    ):
        _require_restore_service_running(completed)


def test_restore_receipt_is_atomic_and_tamper_evident(tmp_path: Path):
    path = tmp_path / "restore-receipt.json"
    written = write_restore_receipt(path, {"state": "accepted", "rto_seconds": 12.5})

    assert read_restore_receipt(path) == written
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["state"] = "rejected"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="restore_receipt_checksum_invalid"):
        read_restore_receipt(path)


def test_restore_database_evidence_requires_install_receipt_relation(
    monkeypatch,
    tmp_path: Path,
):
    source = _restore_source(tmp_path)
    monkeypatch.setattr(
        "scripts.postgres_disposable_restore_core.commands._read_json_query",
        lambda _source, _sql, _error: {
            "tasks": True,
            "task_summary_projection": True,
            "alembic_version": True,
            "pack_install_commit_receipts": False,
        },
    )

    with pytest.raises(
        RuntimeError,
        match="restore_critical_relation_missing:pack_install_commit_receipts",
    ):
        _critical_database_evidence(source)
