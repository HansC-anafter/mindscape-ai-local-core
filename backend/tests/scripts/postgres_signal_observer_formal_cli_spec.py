from __future__ import annotations

import hashlib
import stat
import subprocess
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
    project_formal_gate_receipt,
)
from scripts.maintenance.postgres_signal_observer_core import drill_formal_terminal


POSTGRES_IMAGE = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE = "mindscape-ai-local-core-backend@sha256:" + "b" * 64


class _EqualToCaptureHashInput:
    def __eq__(self, other: object) -> bool:
        return other == "full_raw_subprocess_capture_bytes"


def _config(tmp_path: Path):
    suffix_tail = int(
        hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest(), 16
    ) % 1_000_000
    suffix = f"20991231T{suffix_tail:06d}Z"
    return build_formal_drill_cli_config(
        drill_suffix=suffix,
        temp_root=Path(f"/private/tmp/mindscape-postgres-signal-drill-{suffix}"),
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


def _remove_test_staging(config) -> None:
    for path in (
        config.bootstrap.pgbouncer_userlist_path,
        config.bootstrap.pgbouncer_config_path,
        config.bootstrap.postgres_environment_path,
    ):
        path.unlink(missing_ok=True)
    for path in (
        config.observer.evidence_host_root,
        config.observer.journal_host_root,
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
        config.observer.journal_host_root,
        config.observer.evidence_host_root,
    ]
    assert order == expected
    assert [item.path for item in state.owned_directories] == expected
    assert all(
        stat.S_IMODE(path.lstat().st_mode) == 0o700 for path in expected
    )
    assert len(state.owned_files) == 3
    assert _cleanup_precondition_state(state) is True
    assert all(not path.exists() for path in expected)


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
        if item.path == config.observer.journal_host_root:
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


def _container_readback_pass(*_args, **_kwargs):
    return {
        "validation_passed": True,
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
            assert 0 < timeout <= 10.0
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
    assert receipt["stages"]["pg_isready"]["attempt_count"] == 2
    assert receipt["stages"]["psql_select_one"]["attempt_count"] == 1
    assert (
        receipt["stages"]["psql_select_one"]["last_result"]["terminal_capture"][
            "output_disclosed"
        ]
        is False
    )
    assert executor.calls[0] == ("pg_isready", 10.0)
    assert executor.calls[-1] == ("psql", pytest.approx(9.65))
    assert clock.sleeps == [0.25]
    assert "transient-payload" not in repr(receipt)


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
    assert stage["attempt_count"] == 40
    assert stage["last_result"]["status"] == "terminal_nonzero"
    assert stage["last_result"]["terminal_capture"]["output_disclosed"] is False
    assert receipt["stages"]["psql_select_one"]["attempted"] is False
    assert executor.timeouts[-1] == pytest.approx(0.25)
    assert clock.now == pytest.approx(9.75)
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
                code = 0 if self.pg_count == 40 else 1
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
    assert receipt["stages"]["pg_isready"]["attempt_count"] == 40
    assert receipt["stages"]["psql_select_one"]["attempt_count"] == 1
    assert executor.timeouts[-2] == pytest.approx(0.25)
    assert executor.timeouts[-1] == pytest.approx(0.20)
    assert clock.now == pytest.approx(9.85)
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
    assert executor.pg_count == 40
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
                if self.pg_count == 40:
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
                code = 0 if self.pg_count in {1, 40} else 1
                if self.pg_count == 40:
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
    assert executor.pg_count == 40
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
    assert executor.pg_count == executor.psql_count == 40
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
