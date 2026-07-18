from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance.postgres_signal_observer_core import (
    build_formal_drill_cli_config,
    serialize_disposable_pgbouncer_config,
    validate_formal_exec_result,
)
from scripts.maintenance.postgres_signal_observer_core import drill_formal_cli
from scripts.maintenance.postgres_signal_observer_core import drill_formal_gates
from scripts.maintenance.postgres_signal_observer_core.drill_formal_executor import (
    FormalDockerSubprocessExecutor,
)
from scripts.maintenance.postgres_signal_observer_core.drill_formal_terminal import (
    terminal_finalize,
)


POSTGRES_IMAGE = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
SUFFIX = "20260718T151758Z"


def _config(tmp_path: Path):
    return build_formal_drill_cli_config(
        drill_suffix=SUFFIX,
        temp_root=Path(f"/private/tmp/mindscape-postgres-signal-drill-{SUFFIX}"),
        journal_root=tmp_path / "journal",
        postgres_image_ref=POSTGRES_IMAGE,
        observer_image_ref=OBSERVER_IMAGE,
        repo_root=Path(__file__).resolve().parents[3],
        artifact_sha256="c" * 64,
        source_commit="0123456789abcdef",
        database_user="mindscape",
        database_name="mindscape_core",
        pgbouncer_port=6432,
        sleep_seconds=120,
    )


def test_precondition_revocation_failure_never_forges_owner_handback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        drill_formal_cli,
        "require_runtime_database_mutation_allowed",
        lambda *_args, **_kwargs: SimpleNamespace(
            reason="incident_diagnostic_permit", incident_id="incident-fixture"
        ),
    )
    monkeypatch.setattr(
        drill_formal_cli,
        "prepare_formal_preconditions",
        lambda _config: (_ for _ in ()).throw(RuntimeError("fixture-failure")),
    )

    class Journal:
        def __init__(self, _root):
            pass

        def revoke_diagnostic_permit(self, *_args, **_kwargs):
            raise RuntimeError("revoke-failed")

    monkeypatch.setattr(drill_formal_cli, "RuntimeDatabaseIncidentJournal", Journal)
    monkeypatch.setattr(
        drill_formal_cli,
        "terminal_finalize",
        lambda *_args, **_kwargs: {
            "remaining_resources_verified": True,
            "terminal_owner": "unknown",
            "handed_back": False,
        },
    )

    receipt = drill_formal_cli.execute_canonical_formal_drill(config)

    assert receipt["first_failure"] == "formal_drill_precondition_failed"
    assert receipt["permit_revocation_completed"] is False
    assert receipt["terminal_owner"] == "unknown"
    assert receipt["ownership_handed_back"] is False


def test_remaining_resource_failure_blocks_handback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        calls = 0

        def run(self, _argv, **_kwargs):
            self.calls += 1
            return SimpleNamespace(
                returncode=0,
                stdout=(b"still-present\n" if self.calls == 1 else b""),
            )

    class Journal:
        def __init__(self, _root):
            pass

        def current(self):
            return SimpleNamespace(
                incident_id="incident-fixture", diagnostic_permit=None
            )

        def record_diagnostic_ownership_handback(self, *_args, **_kwargs):
            raise AssertionError("handback must not be recorded")

    monkeypatch.setattr(
        "scripts.maintenance.postgres_signal_observer_core.drill_formal_terminal.RuntimeDatabaseIncidentJournal",
        Journal,
    )
    receipt = terminal_finalize(
        config,
        Executor(),
        [],
        incident_id="incident-fixture",
        terminal_reason="fixture-terminal",
    )

    assert receipt["remaining_resources_verified"] is False
    assert receipt["terminal_owner"] == "unknown"
    assert receipt["handed_back"] is False
    assert len(receipt["resource_readback"]) == 5


def test_client_gate_derives_signal_pid_without_external_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **_kwargs):
            return SimpleNamespace(returncode=0, stdout=b"4242\n", stderr=b"")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {"validation_passed": True},
    )
    executor = Executor()
    gate = drill_formal_gates.FormalDrillGateOwner(config, executor)

    assert gate.evaluate("client_ready")["passed"] is True
    assert executor.signal_config.target_postgres_pid == 4242
    assert executor.signal_config.docker_argv()[-1] == "4242"


def test_generic_nonzero_result_persists_only_raw_capture_hashes() -> None:
    stdout = b"sentinel-secret\xff"
    stderr = b"permission denied\x80"
    source = FormalDockerSubprocessExecutor._source(
        SimpleNamespace(returncode=125, stdout=stdout, stderr=stderr)
    )
    receipt = validate_formal_exec_result(
        source,
        operation_class="docker_create_disposable_isolated_network",
    )

    capture = receipt["terminal_nonzero_capture"]
    assert receipt["exit_code"] == 125
    assert capture["stdout_sha256"] == hashlib.sha256(stdout).hexdigest()
    assert capture["stderr_sha256"] == hashlib.sha256(stderr).hexdigest()
    assert capture["stdout_bytes"] == len(stdout)
    assert capture["stderr_bytes"] == len(stderr)
    assert source["output"] == ""
    assert b"sentinel-secret" not in repr(receipt).encode("utf-8")


def test_pgbouncer_admin_user_matches_byte_exact_precondition_owner() -> None:
    payload = serialize_disposable_pgbouncer_config(
        {
            "POSTGRES_USER": "mindscape",
            "POSTGRES_PASSWORD": "fixture-secret",
            "POSTGRES_DB": "mindscape_core",
        }
    )
    assert b"admin_users = mindscape\n" in payload
    assert b"stats_users" not in payload
