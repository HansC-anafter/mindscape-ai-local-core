from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts.postgres_recovery_drill_core.policy import DrillScope, validate_drill_scope
from scripts.postgres_recovery_drill_core.receipt import read_role_receipt, write_role_receipt
from scripts.postgres_recovery_drill_core.commands import (
    PRIMARY,
    STANDBY,
    _render_pgbouncer_config,
    rebuild_standby,
    switchback,
)


def test_drill_scope_rejects_non_drill_project(tmp_path: Path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="drill_project_label_required"):
        validate_drill_scope(DrillScope("mindscape", compose, tmp_path / "receipts"))


def test_role_receipt_is_atomic_and_checksummed(tmp_path: Path):
    path = tmp_path / "role-receipt.json"
    written = write_role_receipt(
        path,
        {"generation": 1, "primary_service": "postgres-recovery-drill-standby"},
    )
    assert read_role_receipt(path) == written
    assert not path.with_suffix(".json.tmp").exists()


def test_pgbouncer_config_is_rendered_only_from_role_receipt():
    rendered = _render_pgbouncer_config(
        {"primary_service": "postgres-recovery-drill-standby"}
    )
    assert "host=postgres-recovery-drill-standby" in rendered
    assert "default_pool_size = 20" in rendered


def test_rebuild_standby_uses_basebackup_before_restart(monkeypatch, tmp_path: Path):
    scope = validate_drill_scope(
        DrillScope(
            "mindscape-recovery-drill",
            (tmp_path / "docker-compose.yml"),
            tmp_path / "receipts",
        )
    )
    scope.compose_file.write_text("services: {}\n", encoding="utf-8")
    write_role_receipt(
        scope.receipt_dir / "role-receipt.json",
        {"generation": 1, "primary_service": STANDBY, "state": "accepted"},
    )
    calls = []

    def fake_compose(_scope, *args, **_kwargs):
        calls.append(args)
        return CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(
        "scripts.postgres_recovery_drill_core.commands._compose",
        fake_compose,
    )
    monkeypatch.setattr(
        "scripts.postgres_recovery_drill_core.commands._wait_for_sql_truth",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "scripts.postgres_recovery_drill_core.commands._require_replica_caught_up",
        lambda *_args, **_kwargs: None,
    )

    result = rebuild_standby(scope)

    run_call = next(call for call in calls if call and call[0] == "run")
    assert PRIMARY in run_call
    assert "pg_basebackup" in run_call[-1]
    assert ("up", "-d", "--no-deps", PRIMARY) in calls
    assert result["state"] == "standby_rebuilt_caught_up"


def test_switchback_rejects_receipt_without_rebuilt_standby(tmp_path: Path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    scope = validate_drill_scope(
        DrillScope("mindscape-recovery-drill", compose, tmp_path / "receipts")
    )
    write_role_receipt(
        scope.receipt_dir / "role-receipt.json",
        {"generation": 1, "primary_service": STANDBY, "state": "accepted"},
    )

    with pytest.raises(
        RuntimeError,
        match="switchback_requires_rebuilt_caught_up_standby",
    ):
        switchback(scope, operator="test", fence_proof="test fence")
