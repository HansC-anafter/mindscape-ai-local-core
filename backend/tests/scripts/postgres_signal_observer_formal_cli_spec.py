from __future__ import annotations

import hashlib
import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance.postgres_signal_observer_core import (
    DisposableDrillSignalConfig,
    ObserverEvidenceStore,
    build_formal_drill_cli_config,
    serialize_disposable_pgbouncer_config,
    validate_formal_exec_result,
)
from scripts.maintenance.postgres_signal_observer_core import drill_formal_cli
from scripts.maintenance.postgres_signal_observer_core import drill_formal_executor
from scripts.maintenance.postgres_signal_observer_core import drill_formal_gates
from scripts.maintenance.postgres_signal_observer_core.drill_formal_executor import (
    FormalDockerSubprocessExecutor,
)
from scripts.maintenance.postgres_signal_observer_core.drill_escalation import (
    terminal_nonzero_capture_metadata,
)
from scripts.maintenance.postgres_signal_observer_core.drill_formal_terminal import (
    FORMAL_OBSERVER_EVIDENCE_ROOT_MATERIALIZATION_FAILED,
    FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED,
    FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED,
    FORMAL_SECRET_PRECONDITION_SERIALIZATION_FAILED,
    FORMAL_TEMP_ROOT_MATERIALIZATION_FAILED,
    FormalPreconditionFailure,
    FormalPreconditionState,
    _cleanup_precondition_state,
    prepare_formal_preconditions,
    terminal_finalize,
)
from scripts.maintenance.postgres_signal_observer_core.drill_gate_receipt import (
    project_client_container_readback_outcome,
    project_pgbouncer_container_readback_outcome,
    project_formal_gate_receipt,
    project_postgres_container_readback_outcome,
)
from scripts.maintenance.postgres_signal_observer_core import drill_formal_terminal


POSTGRES_IMAGE = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
POSTGRES_STARTUP_DEADLINE_SECONDS = (
    drill_formal_gates.FORMAL_POSTGRES_STARTUP_DEADLINE_SECONDS
)
POSTGRES_STARTUP_POLL_SECONDS = (
    drill_formal_gates.FORMAL_POSTGRES_STARTUP_POLL_SECONDS
)
POSTGRES_MAX_POLL_ATTEMPTS = int(
    POSTGRES_STARTUP_DEADLINE_SECONDS / POSTGRES_STARTUP_POLL_SECONDS
)


class _EqualToCaptureHashInput:
    def __eq__(self, other: object) -> bool:
        return other == "full_raw_subprocess_capture_bytes"


def _config(tmp_path: Path):
    suffix_tail = int(
        hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest(), 16
    ) % 1_000_000
    suffix = f"20991231T{suffix_tail:06d}Z"
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    return build_formal_drill_cli_config(
        drill_suffix=suffix,
        temp_root=Path(f"/private/tmp/mindscape-postgres-signal-drill-{suffix}"),
        journal_root=journal_root,
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


def _remove_test_staging(config) -> None:
    for path in (
        config.bootstrap.pgbouncer_userlist_path,
        config.bootstrap.pgbouncer_config_path,
        config.bootstrap.postgres_environment_path,
    ):
        path.unlink(missing_ok=True)
    for path in (
        config.observer.evidence_host_root,
        config.observer.evidence_host_root.parent,
        config.bootstrap.temp_root,
    ):
        if path.exists():
            path.rmdir()


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
            "local_staging_removed": True,
            "terminal_owner": "unknown",
            "handed_back": False,
        },
    )

    receipt = drill_formal_cli.execute_canonical_formal_drill(config)

    assert receipt["first_failure"] == "formal_drill_precondition_failed"
    assert receipt["permit_revocation_completed"] is False
    assert receipt["terminal_owner"] == "unknown"
    assert receipt["ownership_handed_back"] is False


def test_preconditions_create_exact_observer_roots_in_parent_child_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    order: list[Path] = []
    source_create = drill_formal_terminal._create_directory

    def record(path: Path):
        order.append(path)
        return source_create(path)

    monkeypatch.setattr(drill_formal_terminal, "_create_directory", record)
    state = prepare_formal_preconditions(config)

    expected = [
        config.bootstrap.temp_root,
        config.observer.evidence_host_root.parent,
        config.observer.evidence_host_root,
    ]
    assert order == expected
    assert [item.path for item in state.owned_directories] == expected
    assert all(
        stat.S_IMODE(path.lstat().st_mode) == 0o700 for path in expected
    )
    assert len(state.owned_files) == 3
    assert config.observer.journal_host_root == config.journal_root
    assert config.observer.journal_host_root not in expected
    mounts = [
        config.observer.docker_argv()[index + 1]
        for index, value in enumerate(config.observer.docker_argv()[:-1])
        if value == "--mount"
    ]
    assert (
        f"type=bind,src={config.journal_root.resolve()},"
        "dst=/app/data/runtime-database-incidents"
    ) in mounts
    assert (
        f"type=bind,src={config.observer.evidence_host_root.resolve()},"
        "dst=/app/data/runtime-database-incidents/signal-observer"
    ) in mounts
    assert _cleanup_precondition_state(state) is True
    assert all(not path.exists() for path in expected)
    assert config.journal_root.is_dir()


@pytest.mark.parametrize(
    ("failed_name", "detail_code", "expected_created_directories"),
    [
        (
            "observer-evidence",
            FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED,
            1,
        ),
        (
            "signal-observer",
            FORMAL_OBSERVER_EVIDENCE_ROOT_MATERIALIZATION_FAILED,
            2,
        ),
    ],
)
def test_directory_failure_cleans_only_invocation_owned_ancestors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_name: str,
    detail_code: str,
    expected_created_directories: int,
) -> None:
    config = _config(tmp_path)
    source_create = drill_formal_terminal._create_directory

    def fail_stage(path: Path):
        if path.name == failed_name:
            raise OSError("sentinel-path-payload")
        return source_create(path)

    monkeypatch.setattr(
        drill_formal_terminal, "_create_directory", fail_stage
    )
    with pytest.raises(FormalPreconditionFailure) as captured:
        prepare_formal_preconditions(config)

    failure = captured.value
    assert failure.detail_code == detail_code
    assert failure.cleanup_completed is True
    assert len(failure.state.owned_directories) == expected_created_directories
    assert failure.state.owned_files == ()
    assert not config.bootstrap.temp_root.exists()
    assert "sentinel-path-payload" not in failure.detail_code


def test_secret_file_failure_cleans_files_child_parent_and_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    source_create = drill_formal_terminal.secure_create_precondition
    calls = 0

    def fail_after_first_file(path: Path, payload: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("sentinel-secret-payload")
        source_create(path, payload)

    monkeypatch.setattr(
        drill_formal_terminal,
        "secure_create_precondition",
        fail_after_first_file,
    )
    with pytest.raises(FormalPreconditionFailure) as captured:
        prepare_formal_preconditions(config)

    failure = captured.value
    assert failure.detail_code == FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED
    assert failure.cleanup_completed is True
    assert len(failure.state.owned_files) == 1
    assert all(not item.path.exists() for item in failure.state.owned_files)
    assert not config.bootstrap.temp_root.exists()
    assert "sentinel-secret-payload" not in failure.detail_code


def test_token_generation_failure_uses_stable_serialization_code_and_cleans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        drill_formal_terminal.secrets,
        "token_hex",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("sentinel-token-payload")
        ),
    )

    with pytest.raises(FormalPreconditionFailure) as captured:
        prepare_formal_preconditions(config)

    failure = captured.value
    assert failure.detail_code == FORMAL_SECRET_PRECONDITION_SERIALIZATION_FAILED
    assert failure.cleanup_completed is True
    assert failure.state.owned_files == ()
    assert failure.state.unverified_created_paths == ()
    assert not config.bootstrap.temp_root.exists()
    assert "sentinel-token-payload" not in failure.detail_code


def test_directory_identity_read_failure_blocks_cleanup_and_handback_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    source_read = drill_formal_terminal._read_invocation_owned_path

    def fail_temp_read(path: Path, *, kind: str):
        if path == config.bootstrap.temp_root:
            raise OSError("sentinel-directory-read-payload")
        return source_read(path, kind=kind)

    monkeypatch.setattr(
        drill_formal_terminal,
        "_read_invocation_owned_path",
        fail_temp_read,
    )
    try:
        with pytest.raises(FormalPreconditionFailure) as captured:
            prepare_formal_preconditions(config)

        failure = captured.value
        assert failure.detail_code == FORMAL_TEMP_ROOT_MATERIALIZATION_FAILED
        assert failure.cleanup_completed is False
        assert failure.state.unverified_created_paths == (
            config.bootstrap.temp_root,
        )
        assert config.bootstrap.temp_root.exists()
        assert failure.state.owned_files == ()
    finally:
        _remove_test_staging(config)


def test_directory_identity_validation_failure_cleans_captured_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    source_validate = drill_formal_terminal._validate_invocation_owned_path

    def fail_journal_validation(item, metadata) -> None:
        if item.path == config.observer.evidence_host_root.parent:
            raise RuntimeError("sentinel-directory-validation-payload")
        source_validate(item, metadata)

    monkeypatch.setattr(
        drill_formal_terminal,
        "_validate_invocation_owned_path",
        fail_journal_validation,
    )

    with pytest.raises(FormalPreconditionFailure) as captured:
        prepare_formal_preconditions(config)

    failure = captured.value
    assert failure.detail_code == FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED
    assert failure.cleanup_completed is True
    assert len(failure.state.owned_directories) == 2
    assert failure.state.unverified_created_paths == ()
    assert not config.bootstrap.temp_root.exists()


def test_file_identity_read_failure_is_tracked_and_blocks_cleanup_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    source_read = drill_formal_terminal._read_invocation_owned_path

    def fail_first_file_read(path: Path, *, kind: str):
        if path == config.bootstrap.postgres_environment_path:
            raise OSError("sentinel-file-read-payload")
        return source_read(path, kind=kind)

    monkeypatch.setattr(
        drill_formal_terminal,
        "_read_invocation_owned_path",
        fail_first_file_read,
    )
    try:
        with pytest.raises(FormalPreconditionFailure) as captured:
            prepare_formal_preconditions(config)

        failure = captured.value
        assert failure.detail_code == FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED
        assert failure.cleanup_completed is False
        assert failure.state.unverified_created_paths == (
            config.bootstrap.postgres_environment_path,
        )
        assert config.bootstrap.postgres_environment_path.exists()
        assert failure.state.owned_files == ()
    finally:
        _remove_test_staging(config)


def test_file_identity_validation_failure_cleans_captured_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    source_validate = drill_formal_terminal._validate_invocation_owned_path

    def fail_first_file_validation(item, metadata) -> None:
        if item.path == config.bootstrap.postgres_environment_path:
            raise RuntimeError("sentinel-file-validation-payload")
        source_validate(item, metadata)

    monkeypatch.setattr(
        drill_formal_terminal,
        "_validate_invocation_owned_path",
        fail_first_file_validation,
    )

    with pytest.raises(FormalPreconditionFailure) as captured:
        prepare_formal_preconditions(config)

    failure = captured.value
    assert failure.detail_code == FORMAL_SECRET_PRECONDITION_MATERIALIZATION_FAILED
    assert failure.cleanup_completed is True
    assert len(failure.state.owned_files) == 1
    assert failure.state.unverified_created_paths == ()
    assert not config.bootstrap.temp_root.exists()


def test_preexisting_temp_root_fails_closed_without_deleting_foreign_owner(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config.bootstrap.temp_root.mkdir(mode=0o755)
    try:
        with pytest.raises(FormalPreconditionFailure) as captured:
            prepare_formal_preconditions(config)

        assert captured.value.state.owned_directories == ()
        assert config.bootstrap.temp_root.exists()
    finally:
        config.bootstrap.temp_root.rmdir()


def test_precondition_receipt_uses_stable_detail_without_payload_or_mutation(
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
    source_create = drill_formal_terminal._create_directory

    def fail_parent(path: Path):
        if path.name == "observer-evidence":
            raise OSError("sentinel-exception-and-path-payload")
        return source_create(path)

    monkeypatch.setattr(
        drill_formal_terminal, "_create_directory", fail_parent
    )

    class Journal:
        def __init__(self, _root):
            pass

        def revoke_diagnostic_permit(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(drill_formal_cli, "RuntimeDatabaseIncidentJournal", Journal)
    monkeypatch.setattr(
        drill_formal_cli,
        "terminal_finalize",
        lambda *_args, **_kwargs: {
            "remaining_resources_verified": True,
            "local_staging_removed": True,
            "terminal_owner": "unknown",
            "handed_back": False,
        },
    )

    receipt = drill_formal_cli.execute_canonical_formal_drill(config)
    precondition = receipt["precondition_receipt"]
    assert receipt["first_failure"] == "formal_drill_precondition_failed"
    assert (
        receipt["failure_detail_code"]
        == FORMAL_OBSERVER_JOURNAL_PARENT_MATERIALIZATION_FAILED
    )
    assert precondition["secret_files_created"] == 0
    assert precondition["secret_files_remaining"] == 0
    assert precondition["network_mutation_attempted"] is False
    assert precondition["container_mutation_attempted"] is False
    assert precondition["downstream_mutation_attempted"] is False
    assert precondition["exception_payload_persisted"] is False
    assert precondition["path_payload_persisted"] is False
    assert "sentinel" not in repr(receipt)


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
        FormalPreconditionState(),
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
    readback_calls = []

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **_kwargs):
            return SimpleNamespace(returncode=0, stdout=b"4242\n", stderr=b"")

        def bind_signal_target(self, _config, signal):
            return signal.target_host_pid is None

    def pass_neutralized_client_readback(contract, *_args, **_kwargs):
        expected = contract._expected()
        readback_calls.append(expected)
        assert expected["tmpfs"] == {
            "/tmp": "rw,noexec,nosuid,size=4m",
            "/var/lib/postgresql/data": "rw,noexec,nosuid,size=1m",
        }
        assert expected["mounts"] == []
        return _container_readback_pass(contract)

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        pass_neutralized_client_readback,
    )
    executor = Executor()
    gate = drill_formal_gates.FormalDrillGateOwner(config, executor)

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )
    assert receipt["passed"] is True
    assert receipt["detail_code"] is None
    assert receipt["stages"]["container_readback"]["passed"] is True
    assert receipt["stages"]["source_owned_pid"]["passed"] is True
    assert len(readback_calls) == 1
    assert "4242" not in json.dumps(receipt, sort_keys=True)
    assert executor.signal_config.target_postgres_pid == 4242
    assert executor.signal_config.target_host_pid is None
    assert executor.signal_config.docker_argv()[-1] == "4242"


def test_client_gate_fails_closed_when_signal_target_binding_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout=b"4242\n",
                stderr=b"",
            )

        def bind_signal_target(self, _config, _signal):
            return False

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    gate = drill_formal_gates.FormalDrillGateOwner(config, executor)

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )

    assert receipt["passed"] is False
    assert receipt["detail_code"] == (
        "formal_client_signal_target_binding_failed"
    )
    assert receipt["stages"]["source_owned_pid"]["last_result"] == {
        "status": "result_invalid",
        "error_code": "formal_client_signal_target_binding_failed",
    }
    assert executor.signal_config is None


def test_client_gate_waits_with_fresh_remaining_budget_for_source_owned_pid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()
    calls: list[tuple[float, float]] = []

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **kwargs):
            calls.append((clock.now, kwargs["timeout"]))
            stdout = b"\n" if len(calls) == 1 else b"4242\n"
            return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")

        def bind_signal_target(self, _config, signal):
            return signal.target_host_pid is None

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    gate = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )

    assert receipt["passed"] is True
    assert receipt["poll_seconds"] == 0.25
    assert receipt["stages"]["source_owned_pid"]["attempt_count"] == 2
    assert calls == [(0.0, pytest.approx(10.0)), (0.25, pytest.approx(9.75))]
    assert executor.signal_config.target_postgres_pid == 4242
    assert executor.signal_config.target_host_pid is None


def test_client_gate_empty_pid_exhausts_one_bounded_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()
    calls: list[tuple[float, float]] = []

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **kwargs):
            assert clock.now < 10.0
            calls.append((clock.now, kwargs["timeout"]))
            return SimpleNamespace(returncode=0, stdout=b"\n", stderr=b"")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    gate = drill_formal_gates.FormalDrillGateOwner(
        config,
        Executor(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )

    assert receipt["passed"] is False
    assert receipt["detail_code"] == (
        "formal_client_pid_not_observed_before_deadline"
    )
    assert receipt["stages"]["source_owned_pid"]["attempt_count"] == 41
    assert len(calls) == 41
    assert all(timeout == pytest.approx(10.0 - started) for started, timeout in calls)
    assert clock.now == pytest.approx(9.75)
    assert gate.executor.signal_config is None


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert 0 < seconds <= 0.25
        self.sleeps.append(seconds)
        self.now += seconds


def _container_readback_pass(contract=None, *_args, **_kwargs):
    return {
        "validation_passed": True,
        "role": getattr(contract, "role", "postgres"),
        "first_failure": None,
        "failures": [],
        "projection_schema_version": (
            drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
        ),
        "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
        "terminal_deadline_seconds": (
            drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
        ),
    }


def test_client_gate_container_failure_blocks_pid_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, *_args, **_kwargs):
            raise AssertionError("PID query must remain blocked")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda contract, *_args, **_kwargs: {
            "validation_passed": False,
            "role": contract.role,
            "first_failure": "client_container_readback_state_unready",
            "failures": ["client_container_readback_state_unready"],
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
        },
    )
    gate = drill_formal_gates.FormalDrillGateOwner(config, Executor())

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )

    assert receipt["passed"] is False
    assert receipt["detail_code"] == "formal_client_container_readback_failed"
    assert receipt["stages"]["source_owned_pid"] == {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }


def test_client_gate_projects_pid_terminal_failure_without_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    stdout = b"private-client-pid-output"
    stderr = b"private-client-pid-error"

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **kwargs):
            assert 0 < kwargs["timeout"] <= 10.0
            return SimpleNamespace(returncode=17, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    gate = drill_formal_gates.FormalDrillGateOwner(config, executor)

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )

    assert receipt["passed"] is False
    assert receipt["detail_code"] == "formal_client_pid_query_terminal_nonzero"
    result = receipt["stages"]["source_owned_pid"]["last_result"]
    assert result["exit_code"] == 17
    assert result["terminal_capture"] == terminal_nonzero_capture_metadata(
        stdout, stderr, exit_code=17
    )
    serialized = json.dumps(receipt, sort_keys=True)
    assert stdout.decode("ascii") not in serialized
    assert stderr.decode("ascii") not in serialized
    assert executor.signal_config is None


@pytest.mark.parametrize(
    ("outcome", "expected_detail"),
    [
        (
            subprocess.TimeoutExpired(cmd=("fixture",), timeout=10.0),
            "formal_client_pid_query_terminal_deadline_exceeded",
        ),
        (OSError("private-error"), "formal_client_pid_query_unavailable"),
        (
            SimpleNamespace(returncode=0, stdout=b"not-a-pid", stderr=b""),
            "formal_client_pid_value_invalid",
        ),
    ],
)
def test_client_gate_projects_stable_pid_failure_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: object,
    expected_detail: str,
) -> None:
    config = _config(tmp_path)

    class Executor:
        signal_config = None
        client_environment = {"PGPASSWORD": "fixture-secret"}
        observer_receipt = None

        def run(self, _argv, **_kwargs):
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    gate = drill_formal_gates.FormalDrillGateOwner(config, Executor())

    receipt = project_formal_gate_receipt(
        "client_ready", gate.evaluate("client_ready")
    )

    assert receipt["passed"] is False
    assert receipt["detail_code"] == expected_detail
    assert "private-error" not in json.dumps(receipt, sort_keys=True)


def test_client_gate_projector_rejects_unattempted_container_without_raising() -> None:
    empty_stage = {
        "attempted": False,
        "attempt_count": 0,
        "success_count": 0,
        "passed": False,
        "last_result": None,
    }
    source = {
        "passed": False,
        "gate": "client_ready",
        "detail_code": "formal_client_container_readback_failed",
        "terminal_deadline_seconds": 10.0,
        "poll_seconds": 0.25,
        "stages": {
            "container_readback": dict(empty_stage),
            "source_owned_pid": dict(empty_stage),
        },
    }

    assert project_formal_gate_receipt("client_ready", source) == {
        "name": "client_ready",
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_client_readiness_receipt_invalid",
    }


@pytest.mark.parametrize(
    ("projector", "expected_role", "source_role"),
    [
        (project_postgres_container_readback_outcome, "postgres", None),
        (project_postgres_container_readback_outcome, "postgres", "pgbouncer"),
        (project_postgres_container_readback_outcome, "postgres", 1),
        (project_pgbouncer_container_readback_outcome, "pgbouncer", None),
        (project_pgbouncer_container_readback_outcome, "pgbouncer", "postgres"),
        (project_pgbouncer_container_readback_outcome, "pgbouncer", 1),
        (project_client_container_readback_outcome, "client", None),
        (project_client_container_readback_outcome, "client", "postgres"),
        (project_client_container_readback_outcome, "client", 1),
    ],
)
def test_container_readback_projection_requires_exact_source_role(
    projector,
    expected_role: str,
    source_role: object,
) -> None:
    source = _container_readback_pass(SimpleNamespace(role=expected_role))
    if source_role is None:
        source.pop("role")
    else:
        source["role"] = source_role

    assert projector(source) is None


def test_postgres_readiness_container_failure_blocks_all_child_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "postgres",
            "first_failure": "postgres_container_readback_state_unready",
            "failures": ["postgres_container_readback_state_unready"],
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "projection": {"Config.Env": ["POSTGRES_PASSWORD=sentinel-secret"]},
            "inspect_argv": ["private-inspect-argv"],
        },
    )
    receipt = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )

    assert receipt["passed"] is False
    assert receipt["detail_code"] == "formal_postgres_container_readback_failed"
    assert receipt["stages"]["container_readback"]["attempt_count"] == 1
    assert receipt["stages"]["container_readback"]["last_result"] == {
        "status": "validation_failed",
        "detail_code": "formal_postgres_container_readback_failed",
        "projection_schema_version": (
            drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
        ),
        "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
        "terminal_deadline_seconds": (
            drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
        ),
        "leaf_failure_schema_version": 1,
        "leaf_failure_code": "postgres_container_readback_state_unready",
        "leaf_failure_count": 1,
        "leaf_failure_codes": ["postgres_container_readback_state_unready"],
    }
    assert receipt["stages"]["pg_isready"]["attempted"] is False
    assert receipt["stages"]["psql_select_one"]["attempted"] is False
    assert "sentinel" not in repr(receipt)
    assert "private-inspect-argv" not in repr(receipt)


@pytest.mark.parametrize(
    ("first_failure", "failures"),
    [
        (
            "postgres_container_readback_state_unready",
            ["postgres_container_readback_state_unready"],
        ),
        (
            "postgres_container_readback_user_mismatch",
            [
                "postgres_container_readback_user_mismatch",
                "postgres_container_readback_state_unready",
            ],
        ),
        (
            "formal_postgres_readback_projection_invalid",
            ["formal_postgres_readback_projection_invalid"],
        ),
    ],
)
def test_postgres_readiness_projects_exact_allowlisted_readback_leaf_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_failure: str,
    failures: list[str],
) -> None:
    config = _config(tmp_path)

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "postgres",
            "first_failure": first_failure,
            "failures": failures,
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "projection": {"Config.Env": ["POSTGRES_PASSWORD=sentinel-secret"]},
            "inspect_argv": ["private-inspect-argv"],
            "raw_exception": "private-exception-payload",
        },
    )

    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )
    projected = project_formal_gate_receipt("postgres_readiness", source)
    leaf = projected["stages"]["container_readback"]["last_result"]

    assert projected["passed"] is False
    assert projected["detail_code"] == "formal_postgres_container_readback_failed"
    assert leaf["leaf_failure_code"] == first_failure
    assert leaf["leaf_failure_codes"] == failures
    assert leaf["leaf_failure_count"] == len(failures)
    assert projected["stages"]["pg_isready"]["attempt_count"] == 0
    assert projected["stages"]["psql_select_one"]["attempt_count"] == 0
    assert "POSTGRES_PASSWORD" not in repr(projected)
    assert "private-inspect-argv" not in repr(projected)
    assert "private-exception-payload" not in repr(projected)


def test_postgres_readiness_projects_exact_readback_terminal_nonzero_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    stdout = b"private-readback-output\xff"
    stderr = b"private-readback-error\x80"
    capture = terminal_nonzero_capture_metadata(stdout, stderr, exit_code=17)

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "postgres",
            "first_failure": "formal_postgres_readback_failed",
            "failures": ["formal_postgres_readback_failed"],
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "exit_code": 17,
            "terminal_nonzero_capture": capture,
            "raw_output": stdout,
            "inspect_argv": ["private-inspect-argv"],
        },
    )

    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )
    projected = project_formal_gate_receipt("postgres_readiness", source)
    result = projected["stages"]["container_readback"]["last_result"]

    assert result["leaf_failure_code"] == "formal_postgres_readback_failed"
    assert result["exit_code"] == 17
    assert result["terminal_nonzero_capture"] == capture
    assert projected["stages"]["pg_isready"]["attempt_count"] == 0
    assert projected["stages"]["psql_select_one"]["attempt_count"] == 0
    serialized = repr(projected)
    assert "private-readback-output" not in serialized
    assert "private-readback-error" not in serialized
    assert "private-inspect-argv" not in serialized


@pytest.mark.parametrize(
    "mutation",
    [
        {"stdout_sha256": "invalid"},
        {"exit_code": 18},
        {"exit_code": True},
        {"stdout_present": False},
        {"stdout_bytes": True},
        {
            "stdout_present": False,
            "stdout_bytes": 0,
            "stdout_sha256": "0" * 64,
        },
        {"hash_input": _EqualToCaptureHashInput()},
        {"output_disclosed": True},
        {"captures_truncated": True},
        {"raw_payload": "private"},
    ],
)
def test_postgres_readiness_rejects_malformed_readback_terminal_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, object],
) -> None:
    config = _config(tmp_path)
    capture = terminal_nonzero_capture_metadata(b"private", b"error", exit_code=17)
    capture.update(mutation)

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "postgres",
            "first_failure": "formal_postgres_readback_failed",
            "failures": ["formal_postgres_readback_failed"],
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "exit_code": 17,
            "terminal_nonzero_capture": capture,
        },
    )

    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )

    assert project_formal_gate_receipt("postgres_readiness", source) == {
        "name": "postgres_readiness",
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_postgres_readiness_receipt_invalid",
    }
    assert source["stages"]["pg_isready"]["attempt_count"] == 0
    assert source["stages"]["psql_select_one"]["attempt_count"] == 0


@pytest.mark.parametrize(
    ("first_failure", "failures", "include_capture"),
    [
        (
            "formal_postgres_readback_failed",
            [
                "formal_postgres_readback_failed",
                "postgres_container_readback_state_unready",
            ],
            True,
        ),
        (
            "postgres_container_readback_state_unready",
            ["postgres_container_readback_state_unready"],
            True,
        ),
        (
            "formal_postgres_readback_failed",
            ["formal_postgres_readback_failed"],
            False,
        ),
    ],
)
def test_readback_capture_requires_exact_singleton_terminal_failure_leaf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_failure: str,
    failures: list[str],
    include_capture: bool,
) -> None:
    config = _config(tmp_path)
    readback = {
        "validation_passed": False,
        "role": "postgres",
        "first_failure": first_failure,
        "failures": failures,
        "projection_schema_version": (
            drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
        ),
        "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
        "terminal_deadline_seconds": (
            drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
        ),
    }
    if include_capture:
        readback["exit_code"] = 17
        readback["terminal_nonzero_capture"] = terminal_nonzero_capture_metadata(
            b"private", b"error", exit_code=17
        )

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: readback,
    )

    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )

    assert project_formal_gate_receipt("postgres_readiness", source) == {
        "name": "postgres_readiness",
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_postgres_readiness_receipt_invalid",
    }
    assert source["stages"]["pg_isready"]["attempt_count"] == 0
    assert source["stages"]["psql_select_one"]["attempt_count"] == 0


@pytest.mark.parametrize(
    ("first_failure", "failures"),
    [
        ("unallowlisted-private-code", ["unallowlisted-private-code"]),
        (
            "postgres_container_readback_state_unready",
            ["postgres_container_readback_user_mismatch"],
        ),
        (
            "postgres_container_readback_state_unready",
            [
                "postgres_container_readback_state_unready",
                "postgres_container_readback_state_unready",
            ],
        ),
    ],
)
def test_postgres_readiness_malformed_readback_leaf_fails_receipt_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_failure: str,
    failures: list[str],
) -> None:
    config = _config(tmp_path)

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "postgres",
            "first_failure": first_failure,
            "failures": failures,
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
        },
    )

    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )

    assert project_formal_gate_receipt("postgres_readiness", source) == {
        "name": "postgres_readiness",
        "kind": "gate",
        "passed": False,
        "detail_code": "formal_postgres_readiness_receipt_invalid",
    }
    assert source["stages"]["pg_isready"]["attempt_count"] == 0
    assert source["stages"]["psql_select_one"]["attempt_count"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        {"projection_schema_version": 1},
        {"projection_schema_version": "wrong-schema"},
        {"projection_schema_version": None},
        {"terminal_deadline_seconds": 10},
        {"terminal_deadline_seconds": 9.0},
        {"terminal_deadline_seconds": None},
        {"projection_max_bytes": True},
        {"projection_max_bytes": 32_768.0},
        {"projection_max_bytes": 1},
    ],
)
def test_postgres_readiness_rejects_readback_metadata_drift_before_child_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, object],
) -> None:
    config = _config(tmp_path)
    source_receipt = {
        "validation_passed": False,
        "role": "postgres",
        "first_failure": "postgres_container_readback_state_unready",
        "failures": ["postgres_container_readback_state_unready"],
        "projection_schema_version": (
            drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
        ),
        "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
        "terminal_deadline_seconds": (
            drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
        ),
        **mutation,
    }

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: source_receipt,
    )

    raw = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    assert projected["detail_code"] == "formal_postgres_readiness_receipt_invalid"
    assert raw["stages"]["pg_isready"]["attempt_count"] == 0
    assert raw["stages"]["psql_select_one"]["attempt_count"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        {
            "first_failure": "postgres_container_readback_state_unready",
            "failures": ["postgres_container_readback_state_unready"],
        },
        {"failures": "wrong-type"},
        {"projection_schema_version": "wrong-schema"},
        {"terminal_deadline_seconds": 11.0},
    ],
)
def test_postgres_readiness_rejects_contradictory_success_before_child_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: dict[str, object],
) -> None:
    config = _config(tmp_path)
    source_receipt = {**_container_readback_pass(), **mutation}

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: source_receipt,
    )

    raw = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )

    assert project_formal_gate_receipt("postgres_readiness", raw)[
        "detail_code"
    ] == "formal_postgres_readiness_receipt_invalid"
    assert raw["stages"]["pg_isready"]["attempt_count"] == 0
    assert raw["stages"]["psql_select_one"]["attempt_count"] == 0


def test_postgres_readiness_polls_to_success_with_fresh_remaining_timeouts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.pg_results = [1, 0]
            self.calls: list[tuple[str, float]] = []

        def run(self, argv, **kwargs):
            timeout = float(kwargs["timeout"])
            assert 0 < timeout <= POSTGRES_STARTUP_DEADLINE_SECONDS
            command = "pg_isready" if drill_formal_gates._PG_ISREADY in argv else "psql"
            self.calls.append((command, timeout))
            if command == "pg_isready":
                code = self.pg_results.pop(0)
                if code == 0:
                    clock.now += 0.1
                return SimpleNamespace(
                    returncode=code,
                    stdout=(b"transient-payload" if code else b"ready"),
                    stderr=b"",
                )
            return SimpleNamespace(returncode=0, stdout=b"1\n", stderr=b"")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    receipt = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")

    assert receipt["passed"] is True
    assert receipt["detail_code"] is None
    assert receipt["startup_deadline_seconds"] == 20.0
    assert receipt["stages"]["pg_isready"]["attempt_count"] == 2
    assert receipt["stages"]["psql_select_one"]["attempt_count"] == 1
    assert (
        receipt["stages"]["psql_select_one"]["last_result"]["terminal_capture"][
            "output_disclosed"
        ]
        is False
    )
    assert executor.calls[0] == ("pg_isready", POSTGRES_STARTUP_DEADLINE_SECONDS)
    assert executor.calls[-1] == (
        "psql",
        pytest.approx(POSTGRES_STARTUP_DEADLINE_SECONDS - 0.35),
    )
    assert clock.sleeps == [0.25]
    assert "transient-payload" not in repr(receipt)


@pytest.mark.parametrize(
    ("psql_results", "prior_status", "prior_index"),
    [
        (("terminal_nonzero", "timeout"), "terminal_nonzero", 1),
        (("result_invalid", "timeout"), "result_invalid", 1),
        (
            ("terminal_nonzero", "result_invalid", "timeout"),
            "result_invalid",
            2,
        ),
    ],
)
def test_postgres_readiness_preserves_one_bounded_prior_psql_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    psql_results: tuple[str, ...],
    prior_status: str,
    prior_index: int,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.psql_results = list(psql_results)

        def run(self, argv, **kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
            outcome = self.psql_results.pop(0)
            if outcome == "timeout":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            if outcome == "result_invalid":
                return SimpleNamespace(
                    returncode=17,
                    stdout="private-invalid-payload",
                    stderr=b"",
                )
            return SimpleNamespace(
                returncode=17,
                stdout=b"private-prior-stdout",
                stderr=b"private-prior-stderr",
            )

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        Executor(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")

    stage = raw["stages"]["psql_select_one"]
    assert raw["detail_code"] == "formal_postgres_psql_select_one_deadline_exceeded"
    assert raw["startup_deadline_seconds"] == POSTGRES_STARTUP_DEADLINE_SECONDS
    assert raw["poll_seconds"] == 0.25
    assert stage["attempt_count"] == len(psql_results)
    assert stage["last_result"] == {
        "status": "timeout",
        "error_code": "formal_postgres_psql_select_one_deadline_exceeded",
    }
    assert stage["prior_terminal_attempt_index"] == prior_index
    assert stage["prior_terminal_result"]["status"] == prior_status
    if prior_status == "terminal_nonzero":
        assert stage["prior_terminal_result"]["exit_code"] == 17
        assert stage["prior_terminal_result"]["terminal_capture"][
            "output_disclosed"
        ] is False
    else:
        assert stage["prior_terminal_result"] == {
            "status": "result_invalid",
            "error_code": "formal_postgres_readiness_capture_invalid",
        }
    assert "private-prior-stdout" not in repr(raw)
    assert "private-prior-stderr" not in repr(raw)
    assert "private-invalid-payload" not in repr(raw)


def test_postgres_readiness_final_poll_quantum_is_terminal_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def run(self, _argv, **kwargs):
            timeout = float(kwargs["timeout"])
            assert timeout > 0
            self.timeouts.append(timeout)
            return SimpleNamespace(
                returncode=1,
                stdout=b"not-ready-payload",
                stderr=b"private-detail",
            )

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    receipt = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")

    stage = receipt["stages"]["pg_isready"]
    assert receipt["passed"] is False
    assert receipt["detail_code"] == "formal_postgres_pg_isready_deadline_exceeded"
    assert stage["attempt_count"] == POSTGRES_MAX_POLL_ATTEMPTS
    assert stage["last_result"]["status"] == "terminal_nonzero"
    assert stage["last_result"]["terminal_capture"]["output_disclosed"] is False
    assert receipt["stages"]["psql_select_one"]["attempted"] is False
    assert executor.timeouts[-1] == pytest.approx(0.25)
    assert clock.now == pytest.approx(
        POSTGRES_STARTUP_DEADLINE_SECONDS - POSTGRES_STARTUP_POLL_SECONDS
    )
    assert "not-ready-payload" not in repr(receipt)
    assert "private-detail" not in repr(receipt)


def test_postgres_readiness_final_poll_quantum_can_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.pg_count = 0
            self.timeouts: list[float] = []

        def run(self, argv, **kwargs):
            timeout = float(kwargs["timeout"])
            assert timeout > 0
            self.timeouts.append(timeout)
            if drill_formal_gates._PG_ISREADY in argv:
                self.pg_count += 1
                code = 0 if self.pg_count == POSTGRES_MAX_POLL_ATTEMPTS else 1
                if code == 0:
                    clock.now += 0.05
                return SimpleNamespace(returncode=code, stdout=b"ready", stderr=b"")
            clock.now += 0.05
            return SimpleNamespace(returncode=0, stdout=b"1\n", stderr=b"")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    receipt = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")

    assert receipt["passed"] is True
    assert (
        receipt["stages"]["pg_isready"]["attempt_count"]
        == POSTGRES_MAX_POLL_ATTEMPTS
    )
    assert receipt["stages"]["psql_select_one"]["attempt_count"] == 1
    assert executor.timeouts[-2] == pytest.approx(0.25)
    assert executor.timeouts[-1] == pytest.approx(0.20)
    assert clock.now == pytest.approx(POSTGRES_STARTUP_DEADLINE_SECONDS - 0.15)
    assert receipt["stages"]["psql_select_one"]["last_result"][
        "terminal_capture"
    ]["output_disclosed"] is False


def test_postgres_readiness_container_readback_exception_is_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        def run(self, _argv, **_kwargs):
            raise AssertionError("readiness child command must not run")

    def unavailable(*_args, **_kwargs):
        raise OSError("private readback error")

    monkeypatch.setattr(
        drill_formal_gates, "execute_disposable_container_readback", unavailable
    )
    receipt = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "postgres_readiness"
    )

    assert receipt["detail_code"] == "formal_postgres_container_readback_failed"
    assert receipt["stages"]["container_readback"]["last_result"][
        "leaf_failure_code"
    ] == "formal_postgres_readback_unavailable"
    assert receipt["stages"]["pg_isready"]["attempted"] is False
    assert "private readback error" not in repr(receipt)


def test_postgres_readiness_zero_exit_with_invalid_capture_never_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.pg_count = 0
            self.psql_count = 0

        def run(self, argv, **_kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                self.pg_count += 1
                return SimpleNamespace(returncode=0, stdout="not-bytes", stderr=b"")
            self.psql_count += 1
            return SimpleNamespace(returncode=0, stdout=b"1\n", stderr=b"")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    receipt = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")

    assert receipt["passed"] is False
    assert receipt["stages"]["pg_isready"]["success_count"] == 0
    assert receipt["stages"]["pg_isready"]["last_result"] == {
        "status": "result_invalid",
        "error_code": "formal_postgres_readiness_capture_invalid",
    }
    assert executor.pg_count == POSTGRES_MAX_POLL_ATTEMPTS
    assert executor.psql_count == 0


def test_postgres_readiness_pg_success_at_deadline_preserves_no_psql_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.pg_count = 0
            self.psql_count = 0

        def run(self, argv, **_kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                self.pg_count += 1
                if self.pg_count == POSTGRES_MAX_POLL_ATTEMPTS:
                    clock.now += 0.25
                    return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"")
            self.psql_count += 1
            raise AssertionError("psql must not launch after the deadline")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    detail = "formal_postgres_psql_select_one_not_attempted_deadline_exceeded"
    assert raw["detail_code"] == detail
    assert projected["detail_code"] == detail
    assert projected["detail_code"] != "formal_postgres_readiness_receipt_invalid"
    assert projected["stages"]["pg_isready"]["last_result"]["status"] == "terminal_zero"
    assert projected["stages"]["psql_select_one"]["attempted"] is False
    assert executor.psql_count == 0


def test_postgres_readiness_prior_psql_failure_preserves_final_pg_deadline_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.pg_count = 0
            self.psql_count = 0

        def run(self, argv, **_kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                self.pg_count += 1
                code = (
                    0 if self.pg_count in {1, POSTGRES_MAX_POLL_ATTEMPTS} else 1
                )
                if self.pg_count == POSTGRES_MAX_POLL_ATTEMPTS:
                    clock.now += 0.25
                return SimpleNamespace(returncode=code, stdout=b"ready", stderr=b"")
            self.psql_count += 1
            return SimpleNamespace(returncode=2, stdout=b"", stderr=b"private")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = Executor()
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    detail = "formal_postgres_psql_select_one_not_attempted_deadline_exceeded"
    assert projected["detail_code"] == detail
    assert projected["stages"]["pg_isready"]["success_count"] == 2
    assert projected["stages"]["psql_select_one"]["attempt_count"] == 1
    assert executor.pg_count == POSTGRES_MAX_POLL_ATTEMPTS
    assert executor.psql_count == 1
    assert "private" not in repr(projected)


def test_postgres_readiness_psql_deadline_and_exec_error_are_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class PsqlNonzeroExecutor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.pg_count = 0
            self.psql_count = 0

        def run(self, argv, **_kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                self.pg_count += 1
                return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
            self.psql_count += 1
            return SimpleNamespace(returncode=2, stdout=b"", stderr=b"secret")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    executor = PsqlNonzeroExecutor()
    receipt = drill_formal_gates.FormalDrillGateOwner(
        config,
        executor,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    assert receipt["detail_code"] == "formal_postgres_psql_select_one_deadline_exceeded"
    assert (
        executor.pg_count
        == executor.psql_count
        == POSTGRES_MAX_POLL_ATTEMPTS
    )
    assert receipt["stages"]["psql_select_one"]["last_result"]["exit_code"] == 2
    assert "secret" not in repr(receipt)

    class UnavailableExecutor(PsqlNonzeroExecutor):
        def run(self, _argv, **_kwargs):
            raise OSError("private unavailable detail")

    unavailable = drill_formal_gates.FormalDrillGateOwner(
        config,
        UnavailableExecutor(),
    ).evaluate("postgres_readiness")
    assert unavailable["detail_code"] == "formal_postgres_pg_isready_unavailable"
    assert unavailable["stages"]["pg_isready"]["last_result"] == {
        "status": "exec_error",
        "error_code": "formal_postgres_pg_isready_unavailable",
    }
    assert "private unavailable detail" not in repr(unavailable)

    class TimeoutExecutor(PsqlNonzeroExecutor):
        def run(self, argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"private")

    timed_out = drill_formal_gates.FormalDrillGateOwner(
        config,
        TimeoutExecutor(),
    ).evaluate("postgres_readiness")
    assert timed_out["detail_code"] == "formal_postgres_pg_isready_deadline_exceeded"
    assert timed_out["stages"]["pg_isready"]["last_result"]["status"] == "timeout"
    assert "private" not in repr(timed_out)


def test_postgres_readiness_preserves_prior_psql_nonzero_before_final_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.psql_count = 0

        def run(self, argv, **kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
            self.psql_count += 1
            if self.psql_count == 1:
                return SimpleNamespace(
                    returncode=2,
                    stdout=b"private-stdout",
                    stderr=b"private-stderr",
                )
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        Executor(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    stage = projected["stages"]["psql_select_one"]
    assert stage["attempt_count"] == 2
    assert stage["last_result"] == {
        "status": "timeout",
        "error_code": "formal_postgres_psql_select_one_deadline_exceeded",
    }
    assert stage["prior_terminal_attempt_index"] == 1
    assert stage["prior_terminal_result"]["status"] == "terminal_nonzero"
    assert stage["prior_terminal_result"]["exit_code"] == 2
    assert (
        stage["prior_terminal_result"]["terminal_capture"]["output_disclosed"]
        is False
    )
    assert "private-stdout" not in repr(projected)
    assert "private-stderr" not in repr(projected)


def test_postgres_readiness_preserves_only_most_recent_eligible_psql_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.psql_count = 0

        def run(self, argv, **kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
            self.psql_count += 1
            if self.psql_count == 1:
                return SimpleNamespace(returncode=2, stdout="invalid", stderr=b"")
            if self.psql_count == 2:
                return SimpleNamespace(returncode=3, stdout=b"recent", stderr=b"")
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        Executor(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    stage = projected["stages"]["psql_select_one"]
    assert stage["attempt_count"] == 3
    assert stage["prior_terminal_attempt_index"] == 2
    assert stage["prior_terminal_result"]["status"] == "terminal_nonzero"
    assert stage["prior_terminal_result"]["exit_code"] == 3
    assert not isinstance(stage["prior_terminal_result"], list)
    assert "invalid" not in repr(projected)
    assert "recent" not in repr(projected)


def test_postgres_readiness_preserves_prior_psql_result_invalid_without_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.psql_count = 0

        def run(self, argv, **kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
            self.psql_count += 1
            if self.psql_count == 1:
                return SimpleNamespace(returncode=2, stdout="invalid", stderr=b"")
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        Executor(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    prior = projected["stages"]["psql_select_one"]["prior_terminal_result"]
    assert prior == {
        "status": "result_invalid",
        "error_code": "formal_postgres_readiness_capture_invalid",
    }
    assert "terminal_capture" not in prior


def test_postgres_readiness_success_clears_prior_psql_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()

    class Executor:
        signal_config = None
        client_environment = None
        observer_receipt = None

        def __init__(self) -> None:
            self.psql_count = 0

        def run(self, argv, **_kwargs):
            if drill_formal_gates._PG_ISREADY in argv:
                return SimpleNamespace(returncode=0, stdout=b"ready", stderr=b"")
            self.psql_count += 1
            return SimpleNamespace(
                returncode=0 if self.psql_count == 2 else 2,
                stdout=b"1\n" if self.psql_count == 2 else b"private",
                stderr=b"",
            )

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    raw = drill_formal_gates.FormalDrillGateOwner(
        config,
        Executor(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).evaluate("postgres_readiness")
    projected = project_formal_gate_receipt("postgres_readiness", raw)

    stage = projected["stages"]["psql_select_one"]
    assert projected["passed"] is True
    assert stage["attempt_count"] == 2
    assert stage["prior_terminal_attempt_index"] is None
    assert stage["prior_terminal_result"] is None
    assert "private" not in repr(projected)


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


def test_formal_executor_binds_exact_signal_target_for_observer(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    config.observer.evidence_host_root.mkdir(parents=True)
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=(
                b"PID COMMAND\n"
                b"54909 postgres: mindscape mindscape_core "
                b"172.20.0.2(12345) SELECT\n"
            ),
            stderr=b"",
        )

    signal = DisposableDrillSignalConfig(
        drill_suffix=config.bootstrap.drill_suffix,
        postgres_image_ref=config.bootstrap.postgres_image_ref,
        target_postgres_pid=4242,
    )
    executor = FormalDockerSubprocessExecutor(run=run)

    assert executor.bind_signal_target(config, signal) is True
    assert calls[0][0] == [
        "/usr/local/bin/docker",
        "top",
        config.bootstrap.postgres_container_name,
        "-eo",
        "pid,args",
    ]
    assert calls[0][1]["timeout"] == 10.0
    assert calls[0][1]["shell"] is False
    store = ObserverEvidenceStore(config.observer.evidence_host_root)
    assert store.consume_signal_target(54909) == 4242
    assert store.consume_signal_target(54909) is None


@pytest.mark.parametrize(
    "stdout",
    [
        b"PID COMMAND\n",
        (
            b"PID COMMAND\n"
            b"54909 postgres: mindscape mindscape_core x SELECT\n"
            b"54910 postgres: mindscape mindscape_core y SELECT\n"
        ),
        b"PID COMMAND\n54909 postgres: mindscape wrong_database x SELECT\n",
    ],
)
def test_formal_executor_rejects_ambiguous_or_missing_host_pid(
    tmp_path: Path,
    stdout: bytes,
) -> None:
    config = _config(tmp_path)
    config.observer.evidence_host_root.mkdir(parents=True)
    signal = DisposableDrillSignalConfig(
        drill_suffix=config.bootstrap.drill_suffix,
        postgres_image_ref=config.bootstrap.postgres_image_ref,
        target_postgres_pid=4242,
    )
    executor = FormalDockerSubprocessExecutor(
        run=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=stdout,
            stderr=b"",
        )
    )

    assert executor.bind_signal_target(config, signal) is False
    assert not (config.observer.evidence_host_root / "signal-target.json").exists()


def test_observer_launcher_failure_projects_exact_payload_free_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    raw_receipt = {
        "launched": False,
        "container_started": True,
        "ready": False,
        "container_id": "d" * 64,
        "first_failure": "observer_health_startup_deadline_exceeded",
        "health_failure_detail_code": None,
        "health_journal_observed": True,
        "health_state": "starting",
        "health_startup_phase": "tracefs_prepare",
        "cleanup": {"stop_succeeded": True, "remove_succeeded": True},
        "pgbouncer_admin_environment": {"private": "sentinel-admin-url"},
        "spec": {"private_path": "sentinel-private-path"},
    }
    monkeypatch.setattr(
        drill_formal_executor,
        "launch_disposable_drill_observer",
        lambda *_args, **_kwargs: raw_receipt,
    )
    executor = FormalDockerSubprocessExecutor()
    executor.observer_environment = SimpleNamespace()
    source = executor.execute(
        SimpleNamespace(operation_class="docker_run_disposable_isolated_observer"),
        config=config,
    )
    projected = validate_formal_exec_result(
        source,
        operation_class="docker_run_disposable_isolated_observer",
    )["observer_launch_receipt"]

    assert projected == {
        "schema_version": "mindscape.postgres-signal-observer-formal-launch.v2",
        "launched": False,
        "container_started": True,
        "ready": False,
        "container_id_persisted": False,
        "health_journal_observed": True,
        "health_state": "starting",
        "health_startup_phase": "tracefs_prepare",
        "health_failure_detail_code": None,
        "raw_payload_persisted": False,
        "first_failure": "observer_health_startup_deadline_exceeded",
        "cleanup": {
            "attempted": True,
            "stop_succeeded": True,
            "remove_succeeded": True,
        },
    }
    assert "container_id" not in projected
    assert "sentinel-admin-url" not in repr(projected)
    assert "sentinel-private-path" not in repr(projected)


@pytest.mark.parametrize(
    "overrides",
    [
        {"health_state": ["starting"]},
        {"health_startup_phase": {"secret": "sentinel"}},
        {"health_startup_phase": "trace_pipe_runtime"},
        {"health_journal_observed": 1},
        {"cleanup": {"stop_succeeded": True, "remove_succeeded": "yes"}},
        {"health_failure_detail_code": {"secret": "sentinel"}},
        {"health_failure_detail_code": ["sentinel"]},
        {"health_failure_detail_code": 1},
        {"health_journal_observed": False},
        {"health_journal_observed": False, "health_state": "health_invalid"},
        {"health_state": "ready"},
        {"container_started": False, "container_id": None},
        {
            "first_failure": "observer_health_identity_mismatch",
            "health_state": "starting",
        },
        {
            "first_failure": "fail_closed_observer_error",
            "health_state": "starting",
            "health_failure_detail_code": "observer_error_unclassified",
        },
        {
            "first_failure": "fail_closed_observer_error",
            "health_state": "fail_closed_observer_error",
            "health_failure_detail_code": "observer_error_unclassified_unknown_phase",
        },
        {
            "first_failure": "disposable_drill_observer_launch_unavailable",
            "container_started": False,
            "container_id": None,
            "health_journal_observed": False,
            "health_state": "starting",
            "health_startup_phase": None,
        },
    ],
)
def test_observer_launcher_projection_fails_closed_on_malformed_metadata(
    overrides: dict[str, object],
) -> None:
    raw_receipt = {
        "launched": False,
        "container_started": True,
        "ready": False,
        "container_id": "d" * 64,
        "first_failure": "observer_health_startup_deadline_exceeded",
        "health_failure_detail_code": None,
        "health_journal_observed": True,
        "health_state": "starting",
        "health_startup_phase": "tracefs_prepare",
        "cleanup": {"stop_succeeded": True, "remove_succeeded": True},
        "pgbouncer_admin_environment": {},
        "spec": {},
    }
    raw_receipt.update(overrides)
    receipt = validate_formal_exec_result(
        {
            "exit_code": 1,
            "output": "",
            "failure_code": "observer_health_startup_deadline_exceeded",
            "observer_launch_receipt": raw_receipt,
        },
        operation_class="docker_run_disposable_isolated_observer",
    )

    assert receipt["delivery_allowed"] is False
    assert receipt["first_failure"] == "formal_observer_launch_receipt_invalid"
    assert "observer_launch_receipt" not in receipt
    assert "sentinel" not in repr(receipt)


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


def test_pgbouncer_readiness_container_failure_blocks_child_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, _argv, **_kwargs):
            raise AssertionError("PgBouncer readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "pgbouncer",
            "first_failure": "pgbouncer_container_readback_state_unready",
            "failures": ["pgbouncer_container_readback_state_unready"],
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "projection": {"Config.Env": ["PGPASSWORD=sentinel-secret"]},
        },
    )
    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "pgbouncer_readiness"
    )
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)

    assert projected["detail_code"] == "formal_pgbouncer_container_readback_failed"
    assert projected["stages"]["pg_isready"]["attempt_count"] == 0
    assert projected["stages"]["show_version"]["attempt_count"] == 0
    assert projected["stages"]["container_readback"]["last_result"][
        "leaf_failure_code"
    ] == "pgbouncer_container_readback_state_unready"
    assert "sentinel-secret" not in repr(projected)


def test_pgbouncer_readback_terminal_nonzero_preserves_only_capture_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    stdout = b"private-readback-output"
    stderr = b"private-readback-error"

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, _argv, **_kwargs):
            raise AssertionError("PgBouncer readiness child command must not run")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        lambda *_args, **_kwargs: {
            "validation_passed": False,
            "role": "pgbouncer",
            "first_failure": "formal_pgbouncer_readback_failed",
            "failures": ["formal_pgbouncer_readback_failed"],
            "projection_schema_version": (
                drill_formal_gates.CONTAINER_READBACK_SCHEMA_VERSION
            ),
            "projection_max_bytes": drill_formal_gates.CONTAINER_READBACK_MAX_BYTES,
            "terminal_deadline_seconds": (
                drill_formal_gates.CONTAINER_READBACK_TERMINAL_DEADLINE_SECONDS
            ),
            "exit_code": 125,
            "terminal_nonzero_capture": terminal_nonzero_capture_metadata(
                stdout, stderr, exit_code=125
            ),
        },
    )
    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "pgbouncer_readiness"
    )
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)
    result = projected["stages"]["container_readback"]["last_result"]

    assert result["leaf_failure_code"] == "formal_pgbouncer_readback_failed"
    assert result["exit_code"] == 125
    assert result["terminal_nonzero_capture"]["stdout_sha256"] == hashlib.sha256(
        stdout
    ).hexdigest()
    assert result["terminal_nonzero_capture"]["stderr_sha256"] == hashlib.sha256(
        stderr
    ).hexdigest()
    assert "private-readback" not in repr(projected)


@pytest.mark.parametrize("first_pg_result", ["terminal_nonzero", "result_invalid"])
def test_pgbouncer_readiness_polls_pg_then_show_in_the_same_round(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_pg_result: str,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()
    calls: list[tuple[str, ...]] = []
    call_timeouts: list[tuple[float, float]] = []
    pg_attempts = 0

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, argv, **kwargs):
            nonlocal pg_attempts
            calls.append(tuple(argv))
            call_timeouts.append((clock.now, kwargs["timeout"]))
            clock.now += 0.05
            if drill_formal_gates._PG_ISREADY in argv:
                pg_attempts += 1
                if pg_attempts == 1 and first_pg_result == "result_invalid":
                    return SimpleNamespace(returncode=0, stdout="not-bytes", stderr=b"")
                exit_code = 2 if pg_attempts == 1 else 0
            else:
                exit_code = 0
            return SimpleNamespace(
                returncode=exit_code,
                stdout=b"private-ready-output",
                stderr=b"",
            )

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    source = drill_formal_gates.FormalDrillGateOwner(
        config, Executor(), monotonic=clock.monotonic, sleep=clock.sleep
    ).evaluate("pgbouncer_readiness")
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)

    assert [drill_formal_gates._PG_ISREADY in argv for argv in calls] == [True, True, False]
    assert [timeout for _, timeout in call_timeouts] == pytest.approx(
        [10.0 - started_at for started_at, _ in call_timeouts]
    )
    assert call_timeouts[-1][1] < call_timeouts[-2][1]
    assert clock.sleeps == [0.25]
    assert projected["passed"] is True
    assert projected["poll_seconds"] == 0.25
    assert projected["stages"]["pg_isready"]["attempt_count"] == 2
    assert projected["stages"]["pg_isready"]["success_count"] == 1
    assert projected["stages"]["show_version"]["attempt_count"] == 1
    assert "private" not in repr(projected)


def test_pgbouncer_pg_isready_deadline_blocks_show_and_post_deadline_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()
    call_timeouts: list[tuple[float, float]] = []

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, argv, **kwargs):
            assert drill_formal_gates._PG_ISREADY in argv
            call_timeouts.append((clock.now, kwargs["timeout"]))
            clock.now += min(0.25, kwargs["timeout"])
            return SimpleNamespace(
                returncode=2,
                stdout=b"private-ready-output",
                stderr=b"private-ready-error",
            )

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    source = drill_formal_gates.FormalDrillGateOwner(
        config, Executor(), monotonic=clock.monotonic, sleep=clock.sleep
    ).evaluate("pgbouncer_readiness")
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)

    assert projected["detail_code"] == "formal_pgbouncer_pg_isready_failed"
    assert projected["stages"]["pg_isready"]["attempt_count"] == len(call_timeouts)
    assert projected["stages"]["show_version"]["attempt_count"] == 0
    assert [timeout for _, timeout in call_timeouts] == pytest.approx(
        [10.0 - started_at for started_at, _ in call_timeouts]
    )
    assert all(timeout > 0 for _, timeout in call_timeouts)
    assert clock.now == 10.0
    assert "private-ready" not in repr(projected)


@pytest.mark.parametrize("first_show_result", ["terminal_nonzero", "result_invalid"])
def test_pgbouncer_show_version_retries_within_shared_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_show_result: str,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()
    call_timeouts: list[tuple[float, float]] = []
    show_attempts = 0

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, argv, **kwargs):
            nonlocal show_attempts
            call_timeouts.append((clock.now, kwargs["timeout"]))
            clock.now += 0.05
            if drill_formal_gates._PG_ISREADY in argv:
                exit_code = 0
            else:
                show_attempts += 1
                if show_attempts == 1 and first_show_result == "result_invalid":
                    return SimpleNamespace(returncode=0, stdout="not-bytes", stderr=b"")
                exit_code = 2 if show_attempts == 1 else 0
            return SimpleNamespace(returncode=exit_code, stdout=b"private", stderr=b"")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    source = drill_formal_gates.FormalDrillGateOwner(
        config, Executor(), monotonic=clock.monotonic, sleep=clock.sleep
    ).evaluate("pgbouncer_readiness")
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)

    assert projected["passed"] is True
    assert projected["stages"]["pg_isready"]["attempt_count"] == 2
    assert projected["stages"]["show_version"]["attempt_count"] == 2
    assert [timeout for _, timeout in call_timeouts] == pytest.approx(
        [10.0 - started_at for started_at, _ in call_timeouts]
    )
    assert call_timeouts[1][1] < call_timeouts[0][1]
    assert clock.sleeps == [0.25]
    assert "private" not in repr(projected)


def test_pgbouncer_show_version_failure_exhausts_shared_deadline_with_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    clock = _FakeClock()
    call_timeouts: list[tuple[float, float]] = []

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, argv, **kwargs):
            call_timeouts.append((clock.now, kwargs["timeout"]))
            clock.now += min(0.125, kwargs["timeout"])
            is_pg = drill_formal_gates._PG_ISREADY in argv
            return SimpleNamespace(
                returncode=0 if is_pg else 2,
                stdout=b"private-show-output",
                stderr=b"private-show-error" if not is_pg else b"",
            )

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    source = drill_formal_gates.FormalDrillGateOwner(
        config, Executor(), monotonic=clock.monotonic, sleep=clock.sleep
    ).evaluate("pgbouncer_readiness")
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)

    show_stage = projected["stages"]["show_version"]
    assert projected["detail_code"] == "formal_pgbouncer_show_version_failed"
    assert show_stage["attempt_count"] > 1
    assert show_stage["last_result"]["status"] == "terminal_nonzero"
    assert show_stage["last_result"]["exit_code"] == 2
    assert show_stage["last_result"]["terminal_capture"]["stderr_sha256"] == (
        hashlib.sha256(b"private-show-error").hexdigest()
    )
    assert [timeout for _, timeout in call_timeouts] == pytest.approx(
        [10.0 - started_at for started_at, _ in call_timeouts]
    )
    assert all(timeout > 0 for _, timeout in call_timeouts)
    assert clock.now == 10.0
    assert "private-show" not in repr(projected)


@pytest.mark.parametrize("failure_kind", ["timeout", "exec_error"])
def test_pgbouncer_terminal_child_failure_is_payload_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    config = _config(tmp_path)
    calls = 0

    class Executor:
        client_environment = {"PGPASSWORD": "fixture-secret"}

        def run(self, argv, **kwargs):
            nonlocal calls
            calls += 1
            if failure_kind == "timeout":
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"private")
            raise OSError("private-exec-error")

    monkeypatch.setattr(
        drill_formal_gates,
        "execute_disposable_container_readback",
        _container_readback_pass,
    )
    source = drill_formal_gates.FormalDrillGateOwner(config, Executor()).evaluate(
        "pgbouncer_readiness"
    )
    projected = project_formal_gate_receipt("pgbouncer_readiness", source)

    assert calls == 1
    assert projected["stages"]["pg_isready"]["last_result"]["status"] == failure_kind
    assert projected["stages"]["show_version"]["attempt_count"] == 0
    assert "private" not in repr(projected)
