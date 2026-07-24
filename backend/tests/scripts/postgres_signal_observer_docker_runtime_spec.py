from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_core import (
    CANONICAL_DOCKER_CLI_ENTRY_PATH,
    DisposableDrillBootstrapConfig,
    DisposableDrillClientConfig,
    DisposableDrillObserverConfig,
    DisposableDrillSignalConfig,
    FormalExecutorDockerRuntimeContract,
    canonical_disposable_drill_name,
    canonical_docker_argv,
    execute_formal_postgres_bootstrap,
    validate_canonical_docker_argv,
)
from scripts.maintenance.postgres_signal_observer_core.artifact import (
    OBSERVER_SOURCE_PATHS,
)
from scripts.maintenance.postgres_signal_observer_core import (
    drill_docker_runtime as docker_runtime,
)


POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "b" * 64
DRILL_SUFFIX = "20260718T130005Z"


def _runtime_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FormalExecutorDockerRuntimeContract:
    target = tmp_path / "Docker.app/Contents/Resources/bin/docker"
    entry = tmp_path / "usr/local/bin/docker"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"canonical-docker-cli")
    target.chmod(0o755)
    entry.parent.mkdir(parents=True)
    entry.symlink_to(target)
    monkeypatch.setattr(docker_runtime, "CANONICAL_DOCKER_CLI_ENTRY_PATH", entry)
    monkeypatch.setattr(docker_runtime, "CANONICAL_DOCKER_CLI_TARGET_PATH", target)
    return FormalExecutorDockerRuntimeContract(entry_path=entry, target_path=target)


def test_runtime_contract_binds_exact_entry_target_and_redacted_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _runtime_tree(tmp_path, monkeypatch)

    contract.validate()
    argv = contract.argv(("network", "create", "isolated-network"))
    spec = contract.redacted_spec()

    assert argv == (str(contract.entry_path), "network", "create", "isolated-network")
    assert spec["contract"] == "canonical_local_core_docker_cli_v1"
    assert spec["entry_path"] == str(contract.entry_path)
    assert spec["target_path"] == str(contract.target_path)
    assert spec["entry_is_symlink"] is True
    assert spec["entry_regular_or_symlink"] is True
    assert spec["entry_executable"] is True
    assert len(spec["entry_identity_sha256"]) == 64
    assert spec["target_regular_file"] is True
    assert spec["target_executable"] is True
    assert len(spec["target_sha256"]) == 64
    assert len(spec["argv_prefix_sha256"]) == 64
    assert spec["path_search"] is False
    assert spec["host_environment_override"] is False
    assert spec["fallback"] is False
    assert spec["shell"] is False
    assert spec["second_launcher"] is False


def test_runtime_contract_rejects_entry_target_and_executable_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _runtime_tree(tmp_path, monkeypatch)

    with pytest.raises(
        ValueError,
        match="formal_executor_docker_entry_identity_mismatch",
    ):
        FormalExecutorDockerRuntimeContract(
            entry_path=tmp_path / "other-docker",
            target_path=contract.target_path,
        ).validate()

    unexpected_target = tmp_path / "unexpected-target"
    unexpected_target.write_bytes(b"unexpected")
    unexpected_target.chmod(0o755)
    Path(contract.entry_path).unlink()
    Path(contract.entry_path).symlink_to(unexpected_target)
    with pytest.raises(
        ValueError,
        match="formal_executor_docker_target_identity_mismatch",
    ):
        contract.validate()

    Path(contract.entry_path).unlink()
    Path(contract.entry_path).symlink_to(contract.target_path)
    Path(contract.target_path).chmod(0o644)
    with pytest.raises(
        ValueError,
        match="formal_executor_docker_runtime_not_executable",
    ):
        contract.validate()


def test_canonical_argv_is_path_and_environment_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/missing")
    monkeypatch.setenv("DOCKER_CLI_PATH", "/tmp/forbidden-docker")

    argv = canonical_docker_argv("inspect", "isolated-container")

    assert argv[0] == str(CANONICAL_DOCKER_CLI_ENTRY_PATH)
    assert "/tmp/forbidden-docker" not in argv
    assert validate_canonical_docker_argv(argv) == argv
    with pytest.raises(
        ValueError,
        match="formal_executor_docker_argv_identity_mismatch",
    ):
        validate_canonical_docker_argv(("docker", "inspect", "container"))


def test_facade_fails_before_artifact_when_docker_runtime_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RejectedDockerRuntime:
        def validate(self) -> None:
            raise ValueError("formal_executor_docker_runtime_unavailable")

    monkeypatch.setattr(
        drill_facade,
        "FormalExecutorDockerRuntimeContract",
        RejectedDockerRuntime,
    )
    monkeypatch.setattr(
        drill_facade,
        "canonical_observer_artifact_sha256",
        lambda _root: (_ for _ in ()).throw(AssertionError("artifact must not run")),
    )

    with pytest.raises(
        SystemExit,
        match="formal_executor_docker_runtime_unavailable",
    ):
        drill_facade.main(
            [
                "--print-formal-runtime-spec",
                "--postgres-drill-image-ref",
                POSTGRES_IMAGE_REF,
                "--observer-backend-image-ref",
                OBSERVER_IMAGE_REF,
            ]
        )


def test_facade_prepermit_receipt_exposes_docker_runtime_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = drill_facade.main(
        [
            "--print-formal-runtime-spec",
            "--postgres-drill-image-ref",
            POSTGRES_IMAGE_REF,
            "--observer-backend-image-ref",
            OBSERVER_IMAGE_REF,
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    runtime = payload["formal_executor_docker_runtime"]

    assert exit_code == 0
    assert payload["validation_passed"] is True
    assert payload["mutation_permit"] is False
    assert payload["runtime_mutation"] is False
    assert runtime["entry_path"] == "/usr/local/bin/docker"
    assert runtime["target_path"] == (
        "/Applications/Docker.app/Contents/Resources/bin/docker"
    )
    assert len(runtime["target_sha256"]) == 64
    assert len(runtime["argv_prefix_sha256"]) == 64
    assert runtime["path_search"] is False
    assert runtime["host_environment_override"] is False


def test_all_isolated_operation_classes_share_one_absolute_docker_owner() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    temp_root = Path(f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}")
    bootstrap = DisposableDrillBootstrapConfig(
        drill_suffix=DRILL_SUFFIX,
        temp_root=temp_root,
        postgres_image_ref=POSTGRES_IMAGE_REF,
    )
    client = DisposableDrillClientConfig(
        container_name=canonical_disposable_drill_name("client", DRILL_SUFFIX),
        network_name=canonical_disposable_drill_name("network", DRILL_SUFFIX),
        postgres_image_ref=POSTGRES_IMAGE_REF,
        pgbouncer_host=canonical_disposable_drill_name("pgbouncer", DRILL_SUFFIX),
        pgbouncer_port=6432,
        database_user="mindscape",
        database_name="mindscape_core",
    )
    signal = DisposableDrillSignalConfig(
        drill_suffix=DRILL_SUFFIX,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        target_postgres_pid=123,
    )
    observer = DisposableDrillObserverConfig(
        container_name=canonical_disposable_drill_name("observer", DRILL_SUFFIX),
        pgbouncer_container_name=canonical_disposable_drill_name(
            "pgbouncer", DRILL_SUFFIX
        ),
        observer_image_ref=OBSERVER_IMAGE_REF,
        journal_host_root=repo_root,
        evidence_host_root=repo_root / "backend",
        repo_root=repo_root,
        artifact_sha256="c" * 64,
        source_commit="d" * 40,
    )
    operations = {
        "postgres_run": bootstrap.postgres_docker_argv(),
        "pgbouncer_run": bootstrap.pgbouncer_docker_argv(),
        "client_run": client.docker_argv(),
        "observer_run": observer.docker_argv(),
        "signal_exec": signal.docker_argv(),
        **bootstrap.lifecycle_docker_argv(),
    }

    assert operations
    assert all(
        argv[0] == str(CANONICAL_DOCKER_CLI_ENTRY_PATH)
        for argv in operations.values()
    )
    assert all(Path(argv[0]).is_absolute() for argv in operations.values())
    assert {argv[0] for argv in operations.values()} == {
        str(CANONICAL_DOCKER_CLI_ENTRY_PATH)
    }
    assert {
        "network_create",
        "network_inspect",
        "network_remove",
        "postgres_inspect",
        "postgres_stop",
        "postgres_remove",
        "pgbouncer_inspect",
        "pgbouncer_stop",
        "pgbouncer_remove",
        "observer_inspect",
        "observer_stop",
        "observer_remove",
        "client_inspect",
        "client_stop",
        "client_remove",
    } <= operations.keys()


def test_formal_postgres_executor_rejects_plain_docker_before_secret_read() -> None:
    with pytest.raises(
        RuntimeError,
        match="formal_escalation_postgres_argv_invalid",
    ):
        execute_formal_postgres_bootstrap(
            ("docker", "run", "-d"),
            environment_path=Path("/missing/secret"),
        )


def test_observer_sources_have_no_bare_docker_or_search_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source_root = repo_root / "scripts/maintenance/postgres_signal_observer_core"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(source_root.glob("*.py"))
    )
    facade = (
        repo_root / "scripts/maintenance/postgres_signal_observer_drill.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        '"docker",',
        "shutil.which",
        "command -v",
        "DOCKER_CLI_PATH",
        "shell=True",
    ):
        assert forbidden not in source
    assert facade.count("FormalExecutorDockerRuntimeContract()") == 1
    assert "--docker-cli" not in facade
    assert "--docker-path" not in facade
    assert "--print-formal-runtime-spec" in facade
    assert os.path.isabs(str(CANONICAL_DOCKER_CLI_ENTRY_PATH))
    assert (
        "scripts/maintenance/postgres_signal_observer_core/"
        "drill_docker_runtime.py"
    ) in OBSERVER_SOURCE_PATHS
