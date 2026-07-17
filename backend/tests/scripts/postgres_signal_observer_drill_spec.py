from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from scripts.maintenance.postgres_signal_observer_core import (
    DRILL_APPLICATION_NAME,
    DisposableDrillClientConfig,
    launch_disposable_drill_client,
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
