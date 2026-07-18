from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance.postgres_signal_observer_core import (
    DRILL_APPLICATION_NAME,
    PGBOUNCER_DECLARED_VOLUME_TMPFS,
    POSTGRES_DATA_TMPFS,
    DisposableDrillBootstrapConfig,
    DisposableDrillClientConfig,
    DisposableDrillObserverConfig,
    POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS,
    canonical_disposable_drill_name,
    canonical_observer_artifact_sha256,
    execute_formal_postgres_bootstrap,
    launch_disposable_drill_client,
    launch_disposable_drill_observer,
    normalize_disposable_drill_suffix,
    serialize_postgres_bootstrap_environment,
    validate_disposable_drill_name,
    validate_formal_exec_result,
)
from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_drill import main as drill_facade_main
from scripts.maintenance.postgres_signal_observer_core.drill_observer import (
    OBSERVER_HEALTH_COMMAND,
    OBSERVER_STARTUP_DEADLINE_SECONDS,
)
from scripts.maintenance.postgres_signal_observer_core.evidence import EvidenceBudget
from scripts.maintenance.postgres_signal_observer_core.tracefs import (
    INSTANCE_NAME,
    SIGNAL_FILTER,
)


IMAGE_REF = "mindscape-ai-local-core-postgres@sha256:" + "a" * 64
DRILL_SUFFIX = "20260717T233540Z"


def test_disposable_drill_names_use_one_exact_lowercase_suffix_seam() -> None:
    expected = {
        "network": "runtime-db-observer-drill-20260717t233540z",
        "postgres": "runtime-db-observer-drill-postgres-20260717t233540z",
        "pgbouncer": "runtime-db-observer-drill-pgbouncer-20260717t233540z",
        "observer": "runtime-db-observer-drill-observer-20260717t233540z",
        "client": "runtime-db-observer-drill-client-20260717t233540z",
    }

    assert normalize_disposable_drill_suffix(DRILL_SUFFIX) == "20260717t233540z"
    assert {
        role: canonical_disposable_drill_name(role, DRILL_SUFFIX) for role in expected
    } == expected
    assert len(set(expected.values())) == len(expected)
    assert all(len(name) <= 63 for name in expected.values())
    assert (
        canonical_disposable_drill_name("observer", DRILL_SUFFIX)
        == expected["observer"]
    )
    assert (
        canonical_disposable_drill_name("observer", "20260717T233541Z")
        != expected["observer"]
    )


def test_disposable_drill_name_validator_rejects_uppercase_output() -> None:
    with pytest.raises(ValueError, match="disposable_drill_name_invalid"):
        validate_disposable_drill_name(
            "runtime-db-observer-drill-observer-20260717T233540Z"
        )


def test_disposable_drill_name_builder_has_no_hash_or_fallback_branch() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (
        repo_root / "scripts/maintenance/postgres_signal_observer_core/drill_names.py"
    ).read_text(encoding="utf-8")

    assert "import hashlib" not in source
    assert ".hexdigest(" not in source
    assert "sha256" not in source.lower()


@pytest.mark.parametrize(
    ("role", "suffix"),
    [
        ("observer", "20260717t233540z"),
        ("observer", "20260717T233540"),
        ("observer", "2026-07-17T233540Z"),
        ("observer", ""),
        ("unknown", DRILL_SUFFIX),
    ],
)
def test_disposable_drill_name_builder_rejects_noncanonical_input(
    role: str,
    suffix: str,
) -> None:
    with pytest.raises(ValueError, match="disposable_drill_(suffix|name_role)_invalid"):
        canonical_disposable_drill_name(role, suffix)


@pytest.fixture
def client_config() -> DisposableDrillClientConfig:
    return DisposableDrillClientConfig(
        container_name="postgres-signal-observer-drill-client-1",
        network_name="postgres-signal-observer-drill-network-1",
        image_ref=IMAGE_REF,
        pgbouncer_host="postgres-signal-observer-drill-pgbouncer",
        pgbouncer_port=6432,
        database_user="drill_user",
        database_name="drill_database",
        sleep_seconds=120,
    )


def _parse_psql_argv(argv: tuple[str, ...]) -> argparse.Namespace:
    image_index = argv.index(IMAGE_REF)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-X", action="store_true")
    parser.add_argument("-h")
    parser.add_argument("-p")
    parser.add_argument("-U")
    parser.add_argument("-d")
    parser.add_argument("--set")
    parser.add_argument("--command")
    return parser.parse_args(argv[image_index + 1 :])


def test_client_argv_is_parseable_and_application_name_never_enters_sql(
    client_config: DisposableDrillClientConfig,
) -> None:
    argv = client_config.docker_argv()
    parsed = _parse_psql_argv(argv)

    assert parsed.X is True
    assert parsed.h == "postgres-signal-observer-drill-pgbouncer"
    assert parsed.p == "6432"
    assert parsed.U == "drill_user"
    assert parsed.d == "drill_database"
    assert parsed.set == "ON_ERROR_STOP=1"
    assert parsed.command == "SELECT pg_backend_pid(), pg_sleep(120);"
    assert "SET application_name" not in parsed.command
    assert DRILL_APPLICATION_NAME not in parsed.command
    assert f"PGAPPNAME={DRILL_APPLICATION_NAME}" in argv
    assert "PGPASSWORD" in argv
    assert "sh" not in argv
    assert "-lc" not in argv


def test_launch_stub_receives_secret_only_in_environment_and_receipt_is_redacted(
    client_config: DisposableDrillClientConfig,
) -> None:
    secret = "fixture-only-secret"
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs["shell"] is False
        assert kwargs["env"]["PGPASSWORD"] == secret
        assert secret not in "\0".join(argv)
        _parse_psql_argv(tuple(argv))
        return SimpleNamespace(returncode=0, stdout="b" * 64, stderr="")

    receipt = launch_disposable_drill_client(
        client_config,
        environment={"PGPASSWORD": secret},
        run=fake_run,
    )
    serialized = json.dumps(receipt, sort_keys=True)

    assert len(calls) == 1
    assert receipt["launched"] is True
    assert receipt["spec"]["secret_environment_keys"] == ["PGPASSWORD"]
    assert receipt["spec"]["shell"] is False
    assert secret not in serialized
    assert "SELECT" not in serialized
    assert "pg_sleep" not in serialized


def test_client_config_rejects_payload_injection_and_missing_secret(
    client_config: DisposableDrillClientConfig,
) -> None:
    injected = DisposableDrillClientConfig(
        **{
            **client_config.__dict__,
            "database_name": "drill_database;SELECT current_user",
        }
    )

    with pytest.raises(ValueError, match="database_name_invalid"):
        injected.docker_argv()
    with pytest.raises(ValueError, match="pgpassword_environment_missing"):
        launch_disposable_drill_client(client_config, environment={})


@pytest.fixture
def bootstrap_config(
    request: pytest.FixtureRequest,
) -> DisposableDrillBootstrapConfig:
    config = DisposableDrillBootstrapConfig(
        drill_suffix=DRILL_SUFFIX,
        temp_root=Path(f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}"),
        image_ref=IMAGE_REF,
    )
    request.addfinalizer(
        lambda: config.postgres_environment_path.unlink(missing_ok=True)
    )
    return config


def _option_values(argv: tuple[str, ...], option: str) -> list[str]:
    return [argv[index + 1] for index, value in enumerate(argv) if value == option]


def _valid_pgbouncer_readback(
    config: DisposableDrillBootstrapConfig,
) -> dict[str, object]:
    return {
        "name": f"/{config.pgbouncer_container_name}",
        "config_image": config.image_ref,
        "image_id": config.image_digest,
        "user": "postgres",
        "entrypoint": ["pgbouncer"],
        "cmd": ["/etc/pgbouncer/pgbouncer.ini"],
        "nano_cpus": 100000000,
        "memory_bytes": 33554432,
        "pids_limit": 16,
        "read_only_rootfs": True,
        "security_opt": ["no-new-privileges:true"],
        "tmpfs": {
            "/tmp": "rw,noexec,nosuid,size=4m",
            "/var/lib/postgresql/data": "rw,noexec,nosuid,size=1m",
        },
        "mounts": [
            {
                "type": "bind",
                "source": str(config.pgbouncer_config_path),
                "destination": "/etc/pgbouncer/pgbouncer.ini",
                "rw": False,
            },
            {
                "type": "bind",
                "source": str(config.pgbouncer_userlist_path),
                "destination": "/etc/pgbouncer/userlist.txt",
                "rw": False,
            },
        ],
        "networks": [{"name": config.network_name}],
        "state": {
            "running": True,
            "exit_code": 0,
            "restarting": False,
            "restart_count": 0,
        },
    }


def test_bootstrap_spec_neutralizes_declared_volume_and_preserves_budgets(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    postgres_argv = bootstrap_config.postgres_docker_argv()
    pgbouncer_argv = bootstrap_config.pgbouncer_docker_argv()
    pgbouncer_mounts = _option_values(pgbouncer_argv, "--mount")

    assert _option_values(postgres_argv, "--tmpfs") == [
        POSTGRES_DATA_TMPFS,
        "/var/run/postgresql:rw,nosuid,size=8m",
        "/tmp:rw,noexec,nosuid,size=16m",
    ]
    assert _option_values(pgbouncer_argv, "--tmpfs") == [
        "/tmp:rw,noexec,nosuid,size=4m",
        PGBOUNCER_DECLARED_VOLUME_TMPFS,
    ]
    assert pgbouncer_argv[pgbouncer_argv.index("--cpus") + 1] == "0.10"
    assert pgbouncer_argv[pgbouncer_argv.index("--memory") + 1] == "32m"
    assert pgbouncer_argv[pgbouncer_argv.index("--pids-limit") + 1] == "16"
    assert "--read-only" in pgbouncer_argv
    assert pgbouncer_argv[pgbouncer_argv.index("--security-opt") + 1] == (
        "no-new-privileges:true"
    )
    assert len(pgbouncer_mounts) == 2
    assert all(value.endswith(",readonly") for value in pgbouncer_mounts)
    assert all("/var/lib/postgresql/data" not in value for value in pgbouncer_mounts)
    assert postgres_argv[-1] == pgbouncer_argv[-2] == IMAGE_REF


def test_bootstrap_spec_never_serializes_secret_values(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    secret = "fixture-only-secret"
    spec = bootstrap_config.redacted_spec()
    serialized = json.dumps(spec, sort_keys=True)

    assert secret not in serialized
    assert "postgresql://" not in serialized
    assert spec["postgres_secret_environment_keys"] == [
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    ]
    assert spec["network_name"] == ("runtime-db-observer-drill-20260717t233540z")
    assert spec["postgres_container_name"] == (
        "runtime-db-observer-drill-postgres-20260717t233540z"
    )
    assert spec["pgbouncer_container_name"] == (
        "runtime-db-observer-drill-pgbouncer-20260717t233540z"
    )
    assert spec["observer_container_name"] == (
        "runtime-db-observer-drill-observer-20260717t233540z"
    )
    assert spec["client_container_name"] == (
        "runtime-db-observer-drill-client-20260717t233540z"
    )
    assert spec["postgres_environment_precondition"] == {
        "path": str(bootstrap_config.postgres_environment_path),
        "mode": "0600",
        "grammar": "exact_unquoted_key_value_v1",
        "shell_source": False,
        "atomic_load": "open_once_o_nofollow_fstat_bounded_fd_read",
        "required_keys": list(POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS),
        "values_serialized": False,
    }
    assert "POSTGRES_PASSWORD" in spec["postgres_argv"]
    assert "--env-file" not in spec["postgres_argv"]
    assert "PGPASSWORD" not in spec["pgbouncer_argv"]
    assert spec["pgbouncer_declared_volume_neutralization"] == {
        "path": "/var/lib/postgresql/data",
        "type": "tmpfs",
        "options": "rw,noexec,nosuid,size=1m",
        "budget_bytes": 1048576,
        "path_used_by_pgbouncer": False,
    }


def test_formal_postgres_envelope_loads_non_exported_assignments_atomically(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    path = bootstrap_config.postgres_environment_path
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = "fixture-only-secret+safe"
    assignments = {
        "POSTGRES_USER": "mindscape",
        "POSTGRES_PASSWORD": secret,
        "POSTGRES_DB": "mindscape_core",
    }
    canonical = serialize_postgres_bootstrap_environment(assignments)
    path.write_bytes(canonical)
    assert path.read_bytes() == canonical
    assert canonical == (
        b"POSTGRES_USER=mindscape\n"
        b"POSTGRES_PASSWORD=fixture-only-secret+safe\n"
        b"POSTGRES_DB=mindscape_core\n"
    )
    path.chmod(0o600)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((tuple(argv), kwargs))
        return SimpleNamespace(returncode=0)

    exit_code = execute_formal_postgres_bootstrap(
        bootstrap_config.postgres_docker_argv(),
        environment_path=path,
        base_environment={"PATH": os.environ.get("PATH", "")},
        run=fake_run,
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0][0] == bootstrap_config.postgres_docker_argv()
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["check"] is False
    assert calls[0][1]["env"]["POSTGRES_PASSWORD"] == secret
    assert set(POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS).issubset(calls[0][1]["env"])
    assert "PGPASSWORD" not in calls[0][1]["env"]
    assert secret not in "\0".join(calls[0][0])


@pytest.mark.parametrize(
    "content",
    [
        "POSTGRES_USER=mindscape\nPOSTGRES_DB=mindscape_core\n",
        "POSTGRES_USER=mindscape\nPOSTGRES_PASSWORD=\nPOSTGRES_DB=mindscape_core\n",
        "POSTGRES_USER=mindscape\nPOSTGRES_PASSWORD=secret\nPOSTGRES_DB=\n",
    ],
)
def test_formal_postgres_envelope_rejects_missing_or_empty_required_value(
    bootstrap_config: DisposableDrillBootstrapConfig,
    content: str,
) -> None:
    path = bootstrap_config.postgres_environment_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(
        RuntimeError,
        match="formal_escalation_postgres_environment_required_value_missing",
    ) as failure:
        execute_formal_postgres_bootstrap(
            bootstrap_config.postgres_docker_argv(),
            environment_path=path,
            run=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
        )

    assert "secret" not in str(failure.value)


def test_formal_postgres_envelope_rejects_mode_drift_without_reading_value(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    path = bootstrap_config.postgres_environment_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "POSTGRES_USER=mindscape\n"
        "POSTGRES_PASSWORD=fixture-only-secret\n"
        "POSTGRES_DB=mindscape_core\n",
        encoding="utf-8",
    )
    path.chmod(0o644)

    with pytest.raises(
        RuntimeError,
        match="formal_escalation_postgres_environment_contract_invalid",
    ) as failure:
        execute_formal_postgres_bootstrap(
            bootstrap_config.postgres_docker_argv(),
            environment_path=path,
            run=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
        )

    assert "fixture-only-secret" not in str(failure.value)


def test_formal_postgres_envelope_rejects_symlink_without_following_value(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmp_path: Path,
) -> None:
    target = tmp_path / "secret-target.env"
    target.write_text(
        "POSTGRES_USER=mindscape\n"
        "POSTGRES_PASSWORD=fixture-only-secret\n"
        "POSTGRES_DB=mindscape_core\n",
        encoding="utf-8",
    )
    target.chmod(0o600)
    path = bootstrap_config.postgres_environment_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)

    with pytest.raises(
        RuntimeError,
        match="formal_escalation_postgres_environment_unavailable",
    ) as failure:
        execute_formal_postgres_bootstrap(
            bootstrap_config.postgres_docker_argv(),
            environment_path=path,
            run=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
        )

    assert "fixture-only-secret" not in str(failure.value)


def test_formal_postgres_envelope_keeps_exact_env_key_argv(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    argv = bootstrap_config.postgres_docker_argv()

    assert _option_values(argv, "--env") == list(POSTGRES_BOOTSTRAP_ENVIRONMENT_KEYS)
    assert "--env-file" not in argv
    assert str(bootstrap_config.postgres_environment_path) not in argv


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (
            "POSTGRES_USER=mindscape\nPOSTGRES_PASSWORD=secret\n"
            "POSTGRES_DB=mindscape_core\nPOSTGRES_USER=duplicate\n",
            "formal_escalation_postgres_environment_assignment_duplicate",
        ),
        (
            "POSTGRES_USER=mindscape\nPOSTGRES_PASSWORD=secret\n"
            "POSTGRES_DB=mindscape_core\nPGPASSWORD=unexpected\n",
            "formal_escalation_postgres_environment_assignment_unexpected",
        ),
        (
            "POSTGRES_USER=mindscape\nPOSTGRES_PASSWORD='quoted-secret'\n"
            "POSTGRES_DB=mindscape_core\n",
            "formal_escalation_postgres_environment_value_grammar_invalid",
        ),
        (
            "POSTGRES_USER=mindscape\nPOSTGRES_PASSWORD=secret;command\n"
            "POSTGRES_DB=mindscape_core\n",
            "formal_escalation_postgres_environment_value_grammar_invalid",
        ),
    ],
)
def test_formal_postgres_envelope_rejects_duplicate_or_unexpected_assignment(
    bootstrap_config: DisposableDrillBootstrapConfig,
    content: str,
    reason: str,
) -> None:
    path = bootstrap_config.postgres_environment_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(RuntimeError, match=reason) as failure:
        execute_formal_postgres_bootstrap(
            bootstrap_config.postgres_docker_argv(),
            environment_path=path,
            run=lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
        )

    assert "secret" not in str(failure.value)


def test_pgbouncer_readback_accepts_only_exact_neutralized_mount_contract(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    receipt = bootstrap_config.validate_pgbouncer_readback(
        _valid_pgbouncer_readback(bootstrap_config)
    )

    assert receipt["validation_passed"] is True
    assert receipt["first_failure"] is None
    assert receipt["declared_volume_neutralized"] is True


def test_pgbouncer_readback_rejects_image_declared_anonymous_volume(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    readback = _valid_pgbouncer_readback(bootstrap_config)
    readback["mounts"].append(
        {
            "type": "volume",
            "source": "anonymous-volume-id",
            "destination": "/var/lib/postgresql/data",
            "rw": True,
        }
    )

    receipt = bootstrap_config.validate_pgbouncer_readback(readback)

    assert receipt["validation_passed"] is False
    assert receipt["first_failure"] == ("pgbouncer_bootstrap_anonymous_volume_detected")
    assert receipt["declared_volume_neutralized"] is False


@pytest.mark.parametrize(
    ("tmpfs", "failure"),
    [
        (
            {"/tmp": "rw,noexec,nosuid,size=4m"},
            "pgbouncer_declared_volume_neutralization_missing",
        ),
        (
            {
                "/tmp": "rw,noexec,nosuid,size=4m",
                "/var/lib/postgresql/data": "rw,nosuid,size=2m",
            },
            "pgbouncer_declared_volume_neutralization_drift",
        ),
    ],
)
def test_pgbouncer_readback_rejects_missing_or_drifted_tmpfs(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmpfs: dict[str, str],
    failure: str,
) -> None:
    readback = _valid_pgbouncer_readback(bootstrap_config)
    readback["tmpfs"] = tmpfs

    receipt = bootstrap_config.validate_pgbouncer_readback(readback)

    assert receipt["validation_passed"] is False
    assert receipt["first_failure"] == failure


def test_pgbouncer_readback_rejects_any_extra_mount(
    bootstrap_config: DisposableDrillBootstrapConfig,
) -> None:
    readback = _valid_pgbouncer_readback(bootstrap_config)
    readback["mounts"].append(
        {
            "type": "bind",
            "source": "/tmp/extra",
            "destination": "/tmp/extra",
            "rw": False,
        }
    )

    receipt = bootstrap_config.validate_pgbouncer_readback(readback)

    assert receipt["validation_passed"] is False
    assert receipt["first_failure"] == "pgbouncer_bootstrap_mount_contract_mismatch"


def test_drill_facade_is_the_single_bootstrap_spec_entrypoint(
    bootstrap_config: DisposableDrillBootstrapConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = drill_facade_main(
        [
            "--print-bootstrap-spec",
            "--drill-suffix",
            bootstrap_config.drill_suffix,
            "--temp-root",
            str(bootstrap_config.temp_root),
            "--image-ref",
            bootstrap_config.image_ref,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["pgbouncer_argv"] == list(bootstrap_config.pgbouncer_docker_argv())
    assert payload["postgres_argv"] == list(bootstrap_config.postgres_docker_argv())
    assert payload["artifact_sha256"] == canonical_observer_artifact_sha256(
        Path(__file__).resolve().parents[3]
    )


def test_drill_facade_derives_observer_and_client_names_from_suffix_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    backend_image = "mindscape-ai-local-core-backend@sha256:" + "c" * 64

    observer_exit = drill_facade_main(
        [
            "--print-observer-spec",
            "--drill-suffix",
            DRILL_SUFFIX,
            "--journal-root",
            str(journal_root),
            "--image-ref",
            backend_image,
            "--source-commit",
            "0123456789abcdef",
        ]
    )
    observer_spec = json.loads(capsys.readouterr().out)

    client_exit = drill_facade_main(
        [
            "--print-client-spec",
            "--drill-suffix",
            DRILL_SUFFIX,
            "--image-ref",
            IMAGE_REF,
            "--database-user",
            "drill_user",
            "--database-name",
            "drill_database",
        ]
    )
    client_spec = json.loads(capsys.readouterr().out)

    assert observer_exit == 0
    assert observer_spec["container_name"] == (
        "runtime-db-observer-drill-observer-20260717t233540z"
    )
    assert observer_spec["pgbouncer_container_name"] == (
        "runtime-db-observer-drill-pgbouncer-20260717t233540z"
    )
    assert client_exit == 0
    assert client_spec["container_name"] == (
        "runtime-db-observer-drill-client-20260717t233540z"
    )
    assert client_spec["network_name"] == ("runtime-db-observer-drill-20260717t233540z")
    assert client_spec["pgbouncer_host"] == (
        "runtime-db-observer-drill-pgbouncer-20260717t233540z"
    )


@pytest.mark.parametrize(
    ("legacy_option", "value"),
    [
        ("--container-name", "caller-owned"),
        ("--network-name", "caller-owned"),
        ("--pgbouncer-host", "caller-owned"),
        ("--pgbouncer-container-name", "caller-owned"),
    ],
)
def test_drill_facade_rejects_caller_owned_name_inputs(
    legacy_option: str,
    value: str,
) -> None:
    with pytest.raises(SystemExit):
        drill_facade_main(
            [
                "--print-client-spec",
                "--drill-suffix",
                DRILL_SUFFIX,
                "--image-ref",
                IMAGE_REF,
                "--database-user",
                "drill_user",
                "--database-name",
                "drill_database",
                legacy_option,
                value,
            ]
        )


def test_drill_facade_executes_postgres_through_single_atomic_envelope(
    bootstrap_config: DisposableDrillBootstrapConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_execute(argv, *, environment_path):
        calls.append((tuple(argv), Path(environment_path)))
        return 0

    monkeypatch.setattr(
        drill_facade,
        "execute_formal_postgres_bootstrap",
        fake_execute,
    )

    exit_code = drill_facade.main(
        [
            "--execute-postgres-bootstrap",
            "--drill-suffix",
            bootstrap_config.drill_suffix,
            "--temp-root",
            str(bootstrap_config.temp_root),
            "--image-ref",
            bootstrap_config.image_ref,
        ]
    )

    assert exit_code == 0
    assert calls == [
        (
            bootstrap_config.postgres_docker_argv(),
            bootstrap_config.postgres_environment_path,
        )
    ]


def test_drill_facade_validates_redacted_pgbouncer_readback(
    bootstrap_config: DisposableDrillBootstrapConfig,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    readback_path = tmp_path / "pgbouncer-readback.json"
    readback_path.write_text(
        json.dumps(_valid_pgbouncer_readback(bootstrap_config)),
        encoding="utf-8",
    )

    exit_code = drill_facade_main(
        [
            "--validate-pgbouncer-readback",
            str(readback_path),
            "--drill-suffix",
            bootstrap_config.drill_suffix,
            "--temp-root",
            str(bootstrap_config.temp_root),
            "--image-ref",
            bootstrap_config.image_ref,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["validation_passed"] is True
    assert payload["declared_volume_neutralized"] is True


def test_bootstrap_contract_has_one_facade_and_no_second_launcher() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    maintenance_root = repo_root / "scripts/maintenance"
    facade_hits = []
    launcher_hits = []
    for path in maintenance_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(repo_root).as_posix()
        if "--print-bootstrap-spec" in source:
            facade_hits.append(relative)
        if re.search(r"def\s+launch_[a-z0-9_]*bootstrap", source):
            launcher_hits.append(relative)

    assert facade_hits == ["scripts/maintenance/postgres_signal_observer_drill.py"]
    assert launcher_hits == []


@pytest.mark.parametrize(
    "source",
    [
        {"session_id": 8418, "output": "a" * 64},
        {"session_id": 8418, "output": "a" * 65_537},
        {"output": "a" * 64},
        {"session_id": None, "exit_code": 0, "output": "a" * 64},
    ],
)
def test_formal_exec_gate_requires_terminal_result_before_id_delivery(
    source: dict[str, object],
) -> None:
    receipt = validate_formal_exec_result(
        source,
        operation_class="docker_run_disposable_isolated_postgresql_bootstrap",
    )

    assert receipt["terminal"] is False
    assert receipt["poll_required"] is True
    assert receipt["delivery_allowed"] is False
    assert receipt["first_failure"] == "formal_escalation_cli_nonterminal_result"
    assert "container_id" not in receipt


def test_formal_exec_gate_fails_closed_on_nonzero_terminal_exit() -> None:
    exact_output = "docker: Error response from daemon: No such container: " + "a" * 64
    receipt = validate_formal_exec_result(
        {"exit_code": 125, "output": exact_output},
        operation_class="docker_run_disposable_isolated_postgresql_bootstrap",
    )

    assert receipt["terminal"] is True
    assert receipt["poll_required"] is False
    assert receipt["delivery_allowed"] is False
    assert receipt["exit_code"] == 125
    assert receipt["first_failure"] == "formal_escalation_cli_terminal_failure"
    assert exact_output not in json.dumps(receipt, sort_keys=True)
    assert "container_id" not in receipt


def test_formal_exec_gate_delivers_id_only_after_zero_terminal_exit() -> None:
    container_id = "b" * 64
    receipt = validate_formal_exec_result(
        {"exit_code": 0, "output": container_id + "\n"},
        operation_class="docker_run_disposable_isolated_pgbouncer_bootstrap",
    )

    assert receipt["terminal"] is True
    assert receipt["poll_required"] is False
    assert receipt["delivery_allowed"] is True
    assert receipt["container_id"] == container_id
    assert receipt["first_failure"] is None


def test_drill_facade_is_single_formal_exec_result_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result_path = tmp_path / "formal-result.json"
    result_path.write_text(
        json.dumps({"session_id": 8418, "output": "c" * 64}),
        encoding="utf-8",
    )

    exit_code = drill_facade_main(
        [
            "--validate-formal-exec-result",
            str(result_path),
            "--formal-operation-class",
            "docker_run_disposable_isolated_postgresql_bootstrap",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert payload["poll_required"] is True
    assert payload["delivery_allowed"] is False
    assert "container_id" not in payload
    repo_root = Path(__file__).resolve().parents[3]
    facade_hits = [
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "scripts/maintenance").rglob("*.py")
        if "--validate-formal-exec-result" in path.read_text(encoding="utf-8")
    ]
    assert facade_hits == ["scripts/maintenance/postgres_signal_observer_drill.py"]


@pytest.fixture
def observer_config(tmp_path: Path) -> DisposableDrillObserverConfig:
    repo_root = Path(__file__).resolve().parents[3]
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    return DisposableDrillObserverConfig(
        container_name="postgres-signal-observer-drill-observer-1",
        pgbouncer_container_name="postgres-signal-observer-drill-pgbouncer-1",
        image_ref="mindscape-ai-local-core-backend@sha256:" + "c" * 64,
        journal_host_root=journal_root,
        repo_root=repo_root,
        artifact_sha256=canonical_observer_artifact_sha256(repo_root),
        source_commit="0123456789abcdef",
    )


def test_observer_spec_overrides_image_healthcheck_and_preserves_budgets(
    observer_config: DisposableDrillObserverConfig,
) -> None:
    argv = observer_config.docker_argv()
    joined = "\0".join(argv)

    assert argv[argv.index("--health-cmd") + 1] == OBSERVER_HEALTH_COMMAND
    assert argv[argv.index("--cpus") + 1] == "0.10"
    assert argv[argv.index("--memory") + 1] == "64m"
    assert argv[argv.index("--pids-limit") + 1] == "16"
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
    assert argv[argv.index("--cap-add") + 1] == "SYS_ADMIN"
    assert argv[argv.index("--pid") + 1] == "host"
    assert "--read-only" in argv
    assert "--privileged" not in argv
    assert "docker.sock" not in joined
    assert "PGBOUNCER_ADMIN_URL" in argv
    assert "postgresql://" not in joined
    assert argv[-1] == "/app/scripts/maintenance/postgres_signal_observer.py"
    assert observer_config.redacted_spec()["startup_deadline_seconds"] == 10.0


def test_observer_launcher_accepts_only_ready_canonical_health_journal(
    observer_config: DisposableDrillObserverConfig,
) -> None:
    calls = []
    health = iter(
        [
            {"ready": False, "state": "starting"},
            {
                "ready": True,
                "state": "ready",
                "artifact_sha256": observer_config.artifact_sha256,
                "source_commit": observer_config.source_commit,
                "image_digest": observer_config.image_digest,
                "filter": SIGNAL_FILTER,
                "trace_instance": INSTANCE_NAME,
                "budget_sha256": EvidenceBudget().sha256(),
            },
        ]
    )

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="d" * 64, stderr="")

    receipt = launch_disposable_drill_observer(
        observer_config,
        environment={"PGBOUNCER_ADMIN_URL": "postgresql://fixture-only"},
        run=fake_run,
        read_health=lambda: next(health),
        monotonic=iter([0.0, 0.0, 0.25, 0.25]).__next__,
        sleep=lambda _: None,
    )
    serialized = json.dumps(receipt, sort_keys=True)

    assert receipt["launched"] is True
    assert receipt["ready"] is True
    assert receipt["health_journal_observed"] is True
    assert len(calls) == 1
    assert calls[0][1]["shell"] is False
    assert "postgresql://fixture-only" not in "\0".join(calls[0][0])
    assert "postgresql://fixture-only" not in serialized


def test_observer_launcher_cleans_up_at_existing_ten_second_deadline(
    observer_config: DisposableDrillObserverConfig,
) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        stdout = "e" * 64 if argv[:3] == ["docker", "run", "-d"] else ""
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    receipt = launch_disposable_drill_observer(
        observer_config,
        environment={"PGBOUNCER_ADMIN_URL": "postgresql://fixture-only"},
        run=fake_run,
        read_health=lambda: (_ for _ in ()).throw(
            RuntimeError("observer_health_unavailable")
        ),
        monotonic=iter(
            [
                0.0,
                0.0,
                OBSERVER_STARTUP_DEADLINE_SECONDS,
                OBSERVER_STARTUP_DEADLINE_SECONDS,
            ]
        ).__next__,
        sleep=lambda _: None,
    )

    assert receipt["launched"] is False
    assert receipt["ready"] is False
    assert receipt["first_failure"] == "observer_health_startup_deadline_exceeded"
    assert receipt["health_journal_observed"] is False
    assert receipt["cleanup"] == {
        "stop_succeeded": True,
        "remove_succeeded": True,
    }
    assert [call[0][:2] for call in calls] == [
        ["docker", "run"],
        ["docker", "stop"],
        ["docker", "rm"],
    ]
    assert calls[2][0][2] == "--force"


def test_observer_launcher_rejects_ready_journal_with_wrong_identity(
    observer_config: DisposableDrillObserverConfig,
) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        stdout = "f" * 64 if argv[:3] == ["docker", "run", "-d"] else ""
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    receipt = launch_disposable_drill_observer(
        observer_config,
        environment={"PGBOUNCER_ADMIN_URL": "postgresql://fixture-only"},
        run=fake_run,
        read_health=lambda: {
            "ready": True,
            "state": "ready",
            "artifact_sha256": "0" * 64,
            "source_commit": observer_config.source_commit,
            "image_digest": observer_config.image_digest,
            "filter": SIGNAL_FILTER,
            "trace_instance": INSTANCE_NAME,
            "budget_sha256": EvidenceBudget().sha256(),
        },
        monotonic=iter([0.0, 0.0]).__next__,
        sleep=lambda _: None,
    )

    assert receipt["first_failure"] == "observer_health_identity_mismatch"
    assert receipt["ready"] is False
    assert receipt["cleanup"]["remove_succeeded"] is True
