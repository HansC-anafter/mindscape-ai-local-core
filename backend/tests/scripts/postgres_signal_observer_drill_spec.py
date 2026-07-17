from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance.postgres_signal_observer_core import (
    DRILL_APPLICATION_NAME,
    DisposableDrillClientConfig,
    DisposableDrillObserverConfig,
    canonical_observer_artifact_sha256,
    launch_disposable_drill_client,
    launch_disposable_drill_observer,
)
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
