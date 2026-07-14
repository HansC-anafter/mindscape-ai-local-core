from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts/ci"))

import compose_topology as validator


def _depends(*names: str) -> dict[str, dict[str, object]]:
    return {name: {"condition": "service_healthy", "required": True} for name in names}


def _health(url: str) -> dict[str, object]:
    return {
        "test": [
            "CMD",
            "python",
            "-c",
            f"import urllib.request; urllib.request.urlopen('{url}')",
        ]
    }


def _env(**overrides: str) -> dict[str, str]:
    base = {
        "DATABASE_URL_CORE": "postgresql://mindscape:pw@pgbouncer:6432/mindscape_core",
        "DATABASE_URL_CORE_SESSION": "postgresql://mindscape:pw@postgres:5432/mindscape_core",
        "DATABASE_URL_CORE_READONLY": "postgresql://mindscape:pw@pgbouncer:6432/mindscape_core_readonly",
        "DB_POOL_SIZE": "4",
        "DB_MAX_OVERFLOW": "1",
    }
    base.update(overrides)
    return base


def _runner_env(
    *,
    profile: str,
    accepted_partitions: str,
    max_inflight: str,
    pool_size: str = "4",
    max_overflow: str = "1",
) -> dict[str, str]:
    return _env(
        DB_POOL_SIZE=pool_size,
        DB_MAX_OVERFLOW=max_overflow,
        LOCAL_CORE_RUNNER_PROFILE=profile,
        LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS=accepted_partitions,
        LOCAL_CORE_RUNNER_MAX_INFLIGHT=max_inflight,
    )


def _runner(
    *,
    env: dict[str, str],
    profiles: list[str] | None = None,
) -> dict[str, object]:
    service: dict[str, object] = {
        "environment": env,
        "depends_on": _depends("backend", "pgbouncer", "redis"),
        "entrypoint": ["python", "-m", "backend.app.runner.worker"],
        "healthcheck": {"disable": True},
    }
    if profiles:
        service["profiles"] = profiles
    return service


def _bounded_default_browser_runner() -> dict[str, object]:
    service = _runner(
        env={
            **_runner_env(
                profile="default_local_browser",
                accepted_partitions="default_local_browser",
                max_inflight="1",
            ),
            "LOCAL_CORE_RUNNER_ID": "default-browser-bounded-one",
        }
    )
    service.update(
        {
            "mem_limit": "6442450944",
            "cpus": 4.0,
            "pids_limit": 256,
        }
    )
    return service


def _service_templates() -> dict[str, dict[str, object]]:
    return {
        "postgres": {
            "ports": [{"target": 5432, "published": "5433"}],
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U mindscape"]},
        },
        "pgbouncer": {
            "depends_on": _depends("postgres"),
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -h localhost -p 6432"]},
            "volumes": [{"target": "/etc/pgbouncer/pgbouncer.ini", "read_only": True}],
        },
        "redis": {"healthcheck": {"test": ["CMD", "redis-cli", "ping"]}},
        "backend": {
            "environment": _env(
                MINDSCAPE_BACKEND_ROLE="execution",
                DB_POOL_SIZE="8",
                DB_MAX_OVERFLOW="2",
            ),
            "depends_on": _depends("postgres", "pgbouncer", "redis"),
            "healthcheck": _health("http://localhost:8200/healthz"),
            "ports": [{"target": 8200, "published": "8200"}],
        },
        "backend-control": {
            "profiles": ["control-plane"],
            "environment": _env(
                MINDSCAPE_BACKEND_ROLE="control",
                DB_POOL_SIZE="4",
                DB_MAX_OVERFLOW="2",
            ),
            "depends_on": _depends("postgres", "pgbouncer", "redis"),
            "healthcheck": _health("http://localhost:8210/healthz"),
            "ports": [{"target": 8210, "published": "8220"}],
        },
        "frontend": {
            "profiles": ["control-plane"],
            "depends_on": _depends("backend-control"),
            "healthcheck": {
                "test": [
                    "CMD",
                    "node",
                    "-e",
                    "http.get('http://127.0.0.1:3000/healthz')",
                ]
            },
            "ports": [{"target": 3000, "published": "8300"}],
            "volumes": [{"target": "/app/config", "read_only": True}],
        },
        "postgres-replica": {
            "profiles": ["ha"],
            "depends_on": _depends("postgres"),
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U mindscape"]},
        },
        "runner-default-local-browser": _bounded_default_browser_runner(),
        "runner-browser": _runner(
            env=_runner_env(
                profile="browser_local",
                accepted_partitions="browser_local",
                max_inflight="2",
            )
        ),
        "runner-browser-extra": _runner(
            env=_runner_env(
                profile="browser_local",
                accepted_partitions="browser_local",
                max_inflight="2",
            )
        ),
        "runner-browser-maintenance": _runner(
            env={
                **_runner_env(
                    profile="browser_maintenance",
                    accepted_partitions="browser_local,default_local_browser",
                    max_inflight="1",
                ),
                "LOCAL_CORE_RUNNER_MAINTENANCE_ONLY": "true",
                "LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED": "false",
            }
        ),
        "runner-vision": _runner(
            env=_runner_env(
                profile="vision_local",
                accepted_partitions="vision_local",
                max_inflight="1",
            )
        ),
        "runner-vision-mlx-dev": _runner(
            env=_runner_env(
                profile="vision_mlx_dev",
                accepted_partitions="vision_mlx_dev",
                max_inflight="1",
                pool_size="2",
                max_overflow="0",
            )
        ),
        "runner-spillover": _runner(
            profiles=["spillover"],
            env=_runner_env(
                profile="default_local",
                accepted_partitions="default_local",
                max_inflight="1",
            ),
        ),
        "ocr-service": {
            "profiles": ["ocr"],
            "healthcheck": _health("http://localhost:8001/health"),
        },
        "media-proxy": {},
        "xtts-service": {},
        "whisper-service": {},
    }


def _model(service_names: set[str]) -> dict[str, object]:
    templates = _service_templates()
    return {"services": {name: copy.deepcopy(templates[name]) for name in service_names}}


def _models() -> dict[str, dict[str, object]]:
    expected = validator.EXPECTED_SERVICES_BY_PROFILE
    return {profile: _model(set(services)) for profile, services in expected.items()}


def _pgbouncer_config():
    return validator.parse_pgbouncer_config(
        """
[databases]
mindscape_core = host=postgres port=5432 dbname=mindscape_core
mindscape_vectors = host=postgres port=5432 dbname=mindscape_vectors
mindscape_core_readonly = host=postgres-replica port=5432 dbname=mindscape_core pool_size=10
mindscape_vectors_readonly = host=postgres-replica port=5432 dbname=mindscape_vectors pool_size=5

[pgbouncer]
pool_mode = transaction
max_client_conn = 500
default_pool_size = 30
reserve_pool_size = 10
server_reset_query = DISCARD ALL
"""
    )


def _endpoint_seed() -> dict[str, object]:
    return {
        "endpoints": [
            {
                "service_id": "local_core.execution_api",
                "audience": "container_internal",
                "url": "http://backend:8200",
            },
            {
                "service_id": "local_core.control_api",
                "audience": "container_internal",
                "url": "http://backend-control:8210",
            },
            {
                "service_id": "local_core.control_api",
                "audience": "server_internal",
                "url": "http://backend-control:8210",
            },
            {
                "service_id": "local_core.web_console",
                "audience": "container_internal",
                "url": "http://frontend:3000",
            },
            {
                "service_id": "local_core.web_console",
                "audience": "browser_public",
                "url": "http://localhost:8300",
            },
            {
                "service_id": "local_core.media_proxy",
                "audience": "container_internal",
                "url": "http://media-proxy:8000",
            },
            {
                "service_id": "local_core.postgres_pool",
                "audience": "container_internal",
                "url": "postgresql://pgbouncer:6432",
            },
            {
                "service_id": "local_core.postgres_direct",
                "audience": "container_internal",
                "url": "postgresql://postgres:5432",
            },
        ]
    }


def _validate(models: dict[str, dict[str, object]], seed: dict[str, object] | None = None) -> list[str]:
    return validator.validate_profile_models(
        models,
        pgbouncer_config=_pgbouncer_config(),
        service_endpoint_seed=seed or _endpoint_seed(),
    )


def test_compose_topology_validator_accepts_expected_profile_matrix() -> None:
    assert _validate(_models()) == []


def test_compose_topology_validator_rejects_backend_pool_drift() -> None:
    models = _models()
    backend = models["all-profiles"]["services"]["backend"]
    backend["environment"]["DB_POOL_SIZE"] = "20"

    failures = _validate(models)

    assert any("backend: expected DB_POOL_SIZE='8'" in failure for failure in failures)


def test_compose_topology_validator_rejects_runner_healthcheck_enabled() -> None:
    models = _models()
    runner = models["all-profiles"]["services"]["runner-browser"]
    runner["healthcheck"] = _health("http://localhost:8200/healthz")

    failures = _validate(models)

    assert any("runner-browser: runner healthcheck must remain disabled" in failure for failure in failures)


def test_compose_topology_validator_rejects_default_browser_resource_drift() -> None:
    models = _models()
    runner = models["all-profiles"]["services"]["runner-default-local-browser"]
    runner["environment"]["LOCAL_CORE_RUNNER_ID"] = "default-browser-steady-five"
    runner["mem_limit"] = "25769803776"
    runner["cpus"] = 8.0
    runner["pids_limit"] = 1024

    failures = _validate(models)

    assert any("LOCAL_CORE_RUNNER_ID='default-browser-bounded-one'" in failure for failure in failures)
    assert any("mem_limit='6442450944'" in failure for failure in failures)
    assert any("cpus=4.0" in failure for failure in failures)
    assert any("pids_limit=256" in failure for failure in failures)


def test_compose_topology_validator_rejects_maintenance_role_drift() -> None:
    models = _models()
    runner = models["all-profiles"]["services"]["runner-browser-maintenance"]
    runner["environment"]["LOCAL_CORE_RUNNER_MAINTENANCE_ONLY"] = "false"
    runner["environment"]["LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED"] = "true"

    failures = _validate(models)

    assert any(
        "runner-browser-maintenance: expected LOCAL_CORE_RUNNER_MAINTENANCE_ONLY='true'"
        in failure
        for failure in failures
    )
    assert any(
        "runner-browser-maintenance: expected "
        "LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED='false'" in failure
        for failure in failures
    )


def test_compose_topology_validator_rejects_control_endpoint_drift() -> None:
    seed = _endpoint_seed()
    for endpoint in seed["endpoints"]:
        if endpoint["service_id"] == "local_core.control_api" and endpoint["audience"] == "server_internal":
            endpoint["url"] = "http://backend:8200"

    failures = _validate(_models(), seed=seed)

    assert any("local_core.control_api/server_internal" in failure for failure in failures)


def test_pgbouncer_parser_reads_actual_readonly_aliases() -> None:
    config = validator.parse_pgbouncer_config(
        (REPO_ROOT / "docker/pgbouncer/pgbouncer.ini").read_text(encoding="utf-8")
    )

    assert config.pgbouncer["pool_mode"] == "transaction"
    assert config.databases["mindscape_core_readonly"]["host"] == "postgres-replica"
    assert config.databases["mindscape_core_readonly"]["pool_size"] == "10"


def test_actual_service_endpoint_seed_preserves_core_route_plane() -> None:
    seed = json.loads((REPO_ROOT / "config/service-endpoints.seed.json").read_text(encoding="utf-8"))

    assert validator.validate_service_endpoint_seed(seed) == []
