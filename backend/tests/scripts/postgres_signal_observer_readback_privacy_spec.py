from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.maintenance import postgres_signal_observer_drill as drill_facade
from scripts.maintenance.postgres_signal_observer_core import (
    CANONICAL_DOCKER_CLI_ENTRY_PATH,
    CONTAINER_READBACK_MAX_BYTES,
    CONTAINER_READBACK_SCHEMA_VERSION,
    DisposableDrillBootstrapConfig,
    DisposableDrillClientConfig,
    DisposableDrillContainerReadbackContract,
    DisposableDrillObserverConfig,
    canonical_disposable_drill_name,
    execute_disposable_container_readback,
    parse_container_readback_projection,
)


POSTGRES_IMAGE_REF = "mindscape-ai-local-core-postgres:pg16@sha256:" + "a" * 64
OBSERVER_IMAGE_REF = "mindscape-ai-local-core-backend@sha256:" + "e" * 64
DRILL_SUFFIX = "20260718T134813Z"
SENTINEL_SECRET = "sentinel-secret-must-never-enter-readback"


def _bootstrap() -> DisposableDrillBootstrapConfig:
    return DisposableDrillBootstrapConfig(
        drill_suffix=DRILL_SUFFIX,
        temp_root=Path(f"/private/tmp/mindscape-postgres-signal-drill-{DRILL_SUFFIX}"),
        postgres_image_ref=POSTGRES_IMAGE_REF,
    )


def _projection(role: str = "postgres") -> dict[str, object]:
    return {
        "schema_version": CONTAINER_READBACK_SCHEMA_VERSION,
        "role": role,
        "container_id": "b" * 64,
        "name": f"/runtime-db-observer-drill-{role}-20260718t134813z",
        "config_image": POSTGRES_IMAGE_REF,
        "image_id": "sha256:" + "a" * 64,
        "user": "",
        "entrypoint": ["docker-entrypoint.sh"],
        "cmd": ["postgres"],
        "nano_cpus": 500000000,
        "memory_bytes": 268435456,
        "pids_limit": 64,
        "read_only_rootfs": True,
        "security_opt": ["no-new-privileges:true"],
        "tmpfs": {"/tmp": "rw,noexec,nosuid,size=16m"},
        "mounts": [],
        "cap_add": None,
        "cap_drop": None,
        "privileged": False,
        "pid_mode": "",
        "network_mode": "runtime-db-observer-drill-20260718t134813z",
        "network_id": "c" * 64,
        "network_endpoint_id": "d" * 64,
        "running": True,
        "exit_code": 0,
        "restarting": False,
        "restart_count": 0,
        "started_at": "2026-07-18T13:40:19.000000000Z",
        "status": "running",
        "paused": False,
        "dead": False,
        "oom_killed": False,
        "health_status": "none",
    }


def _raw(source: dict[str, object]) -> bytes:
    return (
        json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


def _contracts() -> dict[str, DisposableDrillContainerReadbackContract]:
    bootstrap = _bootstrap()
    repo_root = Path(__file__).resolve().parents[3]
    observer = DisposableDrillObserverConfig(
        container_name=bootstrap.observer_container_name,
        pgbouncer_container_name=bootstrap.pgbouncer_container_name,
        observer_image_ref=OBSERVER_IMAGE_REF,
        journal_host_root=repo_root,
        repo_root=repo_root,
        artifact_sha256="f" * 64,
        source_commit="1" * 40,
    )
    client = DisposableDrillClientConfig(
        container_name=bootstrap.client_container_name,
        network_name=bootstrap.network_name,
        postgres_image_ref=POSTGRES_IMAGE_REF,
        pgbouncer_host=bootstrap.pgbouncer_container_name,
        pgbouncer_port=6432,
        database_user="mindscape",
        database_name="mindscape_core",
    )
    return {
        "postgres": DisposableDrillContainerReadbackContract(
            role="postgres",
            run_argv=bootstrap.postgres_docker_argv(),
            image_ref=POSTGRES_IMAGE_REF,
        ),
        "pgbouncer": DisposableDrillContainerReadbackContract(
            role="pgbouncer",
            run_argv=bootstrap.pgbouncer_docker_argv(),
            image_ref=POSTGRES_IMAGE_REF,
        ),
        "observer": DisposableDrillContainerReadbackContract(
            role="observer",
            run_argv=observer.docker_argv(),
            image_ref=OBSERVER_IMAGE_REF,
        ),
        "client": DisposableDrillContainerReadbackContract(
            role="client",
            run_argv=client.docker_argv(),
            image_ref=POSTGRES_IMAGE_REF,
        ),
    }


def _valid_contract_projection(
    contract: DisposableDrillContainerReadbackContract,
) -> dict[str, object]:
    expected = contract._expected()
    source = _projection(contract.role)
    for field in (
        "role",
        "name",
        "config_image",
        "image_id",
        "user",
        "entrypoint",
        "cmd",
        "nano_cpus",
        "memory_bytes",
        "pids_limit",
        "read_only_rootfs",
        "security_opt",
        "tmpfs",
        "mounts",
        "cap_add",
        "cap_drop",
        "privileged",
        "pid_mode",
        "network_mode",
    ):
        source[field] = expected[field]
    if expected["attached_network_name"] is None:
        source["network_id"] = ""
        source["network_endpoint_id"] = ""
    source["health_status"] = (
        "starting" if expected["has_healthcheck"] is True else "none"
    )
    return source


def test_all_container_lifecycle_inspect_uses_one_allowlisted_format() -> None:
    operations = _bootstrap().lifecycle_docker_argv()

    for role in ("postgres", "pgbouncer", "observer", "client"):
        argv = operations[f"{role}_inspect"]
        assert argv[:5] == (
            str(CANONICAL_DOCKER_CLI_ENTRY_PATH),
            "inspect",
            "--type",
            "container",
            "--format",
        )
        assert argv[-1].startswith(f"runtime-db-observer-drill-{role}-")
        projection = argv[5]
        assert f'"role":"{role}"' in projection
        assert ".Config.Env" not in projection
        assert ".Config.Labels" not in projection
        assert "{{json .Config}}" not in projection
        assert "{{json .State}}" not in projection
        assert SENTINEL_SECRET not in "\0".join(argv)


def test_parser_accepts_only_one_bounded_allowlisted_line() -> None:
    source = _projection()

    parsed = parse_container_readback_projection(_raw(source))

    assert parsed == source
    assert SENTINEL_SECRET not in json.dumps(parsed, sort_keys=True)


@pytest.mark.parametrize(
    ("mutate", "failure"),
    [
        (
            lambda source: source.update({"Config.Env": [SENTINEL_SECRET]}),
            "drill_container_readback_projection_schema_invalid",
        ),
        (
            lambda source: source.update({"schema_version": "unexpected"}),
            "drill_container_readback_schema_version_invalid",
        ),
        (
            lambda source: source.update({"running": "true"}),
            "drill_container_readback_running_type_invalid",
        ),
        (
            lambda source: source.update(
                {"mounts": [{"type": "bind", "source": "/tmp"}]}
            ),
            "drill_container_readback_mount_schema_invalid",
        ),
    ],
)
def test_parser_rejects_projection_schema_or_type_drift(
    mutate,
    failure: str,
) -> None:
    source = _projection()
    mutate(source)

    with pytest.raises(ValueError, match=failure):
        parse_container_readback_projection(_raw(source))


@pytest.mark.parametrize(
    "raw",
    [
        b"{}",
        b"{}\n{}\n",
        b"x" * (CONTAINER_READBACK_MAX_BYTES + 1),
        b"\xff\n",
    ],
)
def test_parser_rejects_line_size_or_encoding_drift(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_container_readback_projection(raw)


@pytest.mark.parametrize("role", ["postgres", "pgbouncer", "observer", "client"])
def test_four_roles_validate_exact_identity_resources_network_and_state(
    role: str,
) -> None:
    contract = _contracts()[role]
    source = _valid_contract_projection(contract)

    receipt = contract.validate_projection(source)

    assert receipt["validation_passed"] is True
    assert receipt["first_failure"] is None
    assert receipt["container_started"] is True
    assert receipt["projection"] == source


def test_role_validator_rejects_identity_resource_network_and_state_drift() -> None:
    contract = _contracts()["postgres"]
    source = _valid_contract_projection(contract)
    source["user"] = "unexpected"
    source["memory_bytes"] = 1
    source["network_endpoint_id"] = ""
    source["running"] = False

    receipt = contract.validate_projection(source)

    assert receipt["validation_passed"] is False
    assert receipt["first_failure"] == "postgres_container_readback_user_mismatch"
    assert "postgres_container_readback_memory_bytes_mismatch" in receipt["failures"]
    assert (
        "postgres_container_readback_network_identity_mismatch" in receipt["failures"]
    )
    assert "postgres_container_readback_state_unready" in receipt["failures"]


def test_pgbouncer_validator_rejects_tmpfs_or_mount_drift() -> None:
    contract = _contracts()["pgbouncer"]
    source = _valid_contract_projection(contract)
    source["tmpfs"] = {"/tmp": "rw,noexec,nosuid,size=4m"}
    source["mounts"] = [
        *source["mounts"],
        {
            "type": "volume",
            "source": "anonymous-volume",
            "destination": "/var/lib/postgresql/data",
            "rw": True,
        },
    ]

    receipt = contract.validate_projection(source)

    assert receipt["validation_passed"] is False
    assert "pgbouncer_container_readback_tmpfs_mismatch" in receipt["failures"]
    assert "pgbouncer_container_readback_mounts_mismatch" in receipt["failures"]


@pytest.mark.parametrize("role", ["postgres", "pgbouncer", "observer", "client"])
def test_formal_executor_persists_only_allowlisted_projection(
    role: str,
) -> None:
    contract = _contracts()[role]
    safe_projection = _valid_contract_projection(contract)
    hidden_container_metadata = {"Config.Env": [f"POSTGRES_PASSWORD={SENTINEL_SECRET}"]}
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((tuple(argv), kwargs, hidden_container_metadata))
        return SimpleNamespace(returncode=0, stdout=_raw(safe_projection), stderr=b"")

    receipt = execute_disposable_container_readback(contract, run=fake_run)

    assert receipt["validation_passed"] is True
    assert receipt["raw_inspect_json_captured"] is False
    assert receipt["config_env_captured"] is False
    assert receipt["secret_value_or_hash_persisted"] is False
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["text"] is False
    assert SENTINEL_SECRET not in json.dumps(receipt, sort_keys=True)
    assert ".Config.Env" not in "\0".join(calls[0][0])


def test_projection_failure_is_terminal_without_retry_or_payload() -> None:
    contract = _contracts()["postgres"]
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=b'{"Config.Env":["POSTGRES_PASSWORD=sentinel"]}\n',
            stderr=b"",
        )

    receipt = execute_disposable_container_readback(contract, run=fake_run)

    assert len(calls) == 1
    assert receipt["validation_passed"] is False
    assert receipt["first_failure"] == "formal_postgres_readback_projection_invalid"
    assert "Config.Env" not in json.dumps(receipt, sort_keys=True)
    assert "sentinel" not in json.dumps(receipt, sort_keys=True)


def test_facade_routes_postgres_readback_through_single_projection_owner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[DisposableDrillContainerReadbackContract] = []

    def fake_execute(
        contract: DisposableDrillContainerReadbackContract,
    ) -> dict[str, object]:
        calls.append(contract)
        return {
            "validation_passed": True,
            "first_failure": None,
            "failures": [],
            "role": contract.role,
            "raw_inspect_json_captured": False,
            "config_env_captured": False,
            "secret_value_or_hash_persisted": False,
        }

    monkeypatch.setattr(
        drill_facade,
        "execute_disposable_container_readback",
        fake_execute,
    )
    bootstrap = _bootstrap()

    exit_code = drill_facade.main(
        [
            "--execute-container-readback",
            "postgres",
            "--drill-suffix",
            DRILL_SUFFIX,
            "--temp-root",
            str(bootstrap.temp_root),
            "--postgres-drill-image-ref",
            POSTGRES_IMAGE_REF,
            "--observer-backend-image-ref",
            OBSERVER_IMAGE_REF,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0].role == "postgres"
    assert calls[0].run_argv == bootstrap.postgres_docker_argv()
    assert payload["raw_inspect_json_captured"] is False
    assert payload["config_env_captured"] is False
    assert payload["secret_value_or_hash_persisted"] is False
    assert SENTINEL_SECRET not in json.dumps(payload, sort_keys=True)


def test_source_has_one_projection_facade_and_no_raw_inspect_alternate() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    maintenance_root = repo_root / "scripts/maintenance"
    mode_hits: list[str] = []
    projection_owner_hits: list[str] = []

    for path in maintenance_root.rglob("*.py"):
        relative = path.relative_to(repo_root).as_posix()
        source = path.read_text(encoding="utf-8")
        if "--execute-container-readback" in source:
            mode_hits.append(relative)
        if '"--format",\n        projection' in source:
            projection_owner_hits.append(relative)
        if "postgres_signal_observer" in relative:
            assert ".Config.Env" not in source
            assert ".Config.Labels" not in source

    assert mode_hits == ["scripts/maintenance/postgres_signal_observer_drill.py"]
    assert projection_owner_hits == [
        "scripts/maintenance/postgres_signal_observer_core/"
        "drill_readback_projection.py"
    ]
