from __future__ import annotations

import hashlib
import stat
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
from scripts.maintenance.postgres_signal_observer_core import drill_formal_terminal


POSTGRES_IMAGE = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
def _config(tmp_path: Path):
    suffix_tail = int(
        hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest(), 16
    ) % 1_000_000
    suffix = f"20260718T{suffix_tail:06d}Z"
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
