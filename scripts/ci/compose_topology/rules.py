"""Pure Compose topology validation rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contract import (
    CORE_DEPENDENCIES,
    EXPECTED_SERVICES_BY_PROFILE,
    RUNNER_DEPENDENCIES,
    RUNNER_EXPECTATIONS,
    PgBouncerConfig,
)


def _failure(message: str, failures: list[str]) -> None:
    failures.append(message)


def _service(model: Mapping[str, Any], service_name: str) -> Mapping[str, Any]:
    services = model.get("services")
    if not isinstance(services, Mapping):
        return {}
    service = services.get(service_name)
    return service if isinstance(service, Mapping) else {}


def service_names(model: Mapping[str, Any]) -> set[str]:
    services = model.get("services")
    if not isinstance(services, Mapping):
        return set()
    return {str(name) for name in services}


def _profiles(service: Mapping[str, Any]) -> list[str]:
    profiles = service.get("profiles") or []
    if isinstance(profiles, str):
        return [profiles]
    return [str(item) for item in profiles] if isinstance(profiles, Sequence) else []


def _environment(service: Mapping[str, Any]) -> dict[str, str]:
    environment = service.get("environment") or {}
    if isinstance(environment, Mapping):
        return {str(key): str(value) for key, value in environment.items()}
    if isinstance(environment, Sequence) and not isinstance(environment, str):
        parsed: dict[str, str] = {}
        for item in environment:
            key, separator, value = str(item).partition("=")
            if separator:
                parsed[key] = value
        return parsed
    return {}


def _healthcheck_text(service: Mapping[str, Any]) -> str:
    healthcheck = service.get("healthcheck") or {}
    if not isinstance(healthcheck, Mapping):
        return ""
    test = healthcheck.get("test") or []
    if isinstance(test, str):
        return test
    if isinstance(test, Sequence):
        return " ".join(str(item) for item in test)
    return ""


def _healthcheck_disabled(service: Mapping[str, Any]) -> bool:
    healthcheck = service.get("healthcheck") or {}
    return isinstance(healthcheck, Mapping) and healthcheck.get("disable") is True


def _depends_condition(service: Mapping[str, Any], dependency: str) -> str:
    depends_on = service.get("depends_on") or {}
    if isinstance(depends_on, Mapping):
        value = depends_on.get(dependency)
        if isinstance(value, Mapping):
            return str(value.get("condition") or "")
        if value is not None:
            return "service_started"
    if isinstance(depends_on, Sequence) and not isinstance(depends_on, str) and dependency in depends_on:
        return "service_started"
    return ""


def _has_port(service: Mapping[str, Any], *, target: int, published: str) -> bool:
    ports = service.get("ports") or []
    if not isinstance(ports, Sequence) or isinstance(ports, str):
        return False
    for port in ports:
        if isinstance(port, Mapping):
            if str(port.get("target")) == str(target) and str(port.get("published")) == published:
                return True
            continue
        value = str(port)
        if value == f"{published}:{target}" or (
            value.endswith(f":{target}") and value.startswith(published)
        ):
            return True
    return False


def _has_readonly_volume(service: Mapping[str, Any], target: str) -> bool:
    volumes = service.get("volumes") or []
    if not isinstance(volumes, Sequence) or isinstance(volumes, str):
        return False
    for volume in volumes:
        if isinstance(volume, Mapping):
            if volume.get("target") == target and volume.get("read_only") is True:
                return True
            continue
        parts = str(volume).split(":")
        if len(parts) >= 3 and parts[1] == target and parts[2] == "ro":
            return True
    return False


def _require_env(
    service_name: str,
    env: Mapping[str, str],
    key: str,
    expected: str,
    failures: list[str],
) -> None:
    actual = env.get(key)
    if actual != expected:
        _failure(f"{service_name}: expected {key}={expected!r}, got {actual!r}", failures)


def _require_env_contains(
    service_name: str,
    env: Mapping[str, str],
    key: str,
    expected_fragment: str,
    failures: list[str],
) -> None:
    actual = env.get(key, "")
    if expected_fragment not in actual:
        _failure(
            f"{service_name}: expected {key} to contain {expected_fragment!r}, got {actual!r}",
            failures,
        )


def _seed_url(seed: Mapping[str, Any], service_id: str, audience: str) -> str:
    endpoints = seed.get("endpoints") or []
    if not isinstance(endpoints, Sequence) or isinstance(endpoints, str):
        return ""
    for endpoint in endpoints:
        if isinstance(endpoint, Mapping) and endpoint.get("service_id") == service_id:
            if endpoint.get("audience") == audience:
                return str(endpoint.get("url") or "")
    return ""


def validate_service_sets(models: Mapping[str, Mapping[str, Any]]) -> list[str]:
    failures: list[str] = []
    for profile_name, expected_services in EXPECTED_SERVICES_BY_PROFILE.items():
        actual_services = service_names(models.get(profile_name, {}))
        missing = sorted(expected_services - actual_services)
        extra = sorted(actual_services - expected_services)
        if missing or extra:
            _failure(f"{profile_name}: service set drift; missing={missing}; extra={extra}", failures)
    return failures


def validate_backend_planes(model: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    backend = _service(model, "backend")
    backend_env = _environment(backend)
    _require_env("backend", backend_env, "MINDSCAPE_BACKEND_ROLE", "execution", failures)
    _require_env("backend", backend_env, "DB_POOL_SIZE", "8", failures)
    _require_env("backend", backend_env, "DB_MAX_OVERFLOW", "2", failures)
    _require_env_contains("backend", backend_env, "DATABASE_URL_CORE", "@pgbouncer:6432/mindscape_core", failures)
    _require_env_contains("backend", backend_env, "DATABASE_URL_CORE_SESSION", "@postgres:5432/mindscape_core", failures)
    _require_env_contains("backend", backend_env, "DATABASE_URL_CORE_READONLY", "@pgbouncer:6432/mindscape_core_readonly", failures)
    for dependency in CORE_DEPENDENCIES:
        if _depends_condition(backend, dependency) != "service_healthy":
            _failure(f"backend: {dependency} dependency must be service_healthy", failures)
    if "8200/healthz" not in _healthcheck_text(backend):
        _failure("backend: healthcheck must probe 8200/healthz", failures)
    if not _has_port(backend, target=8200, published="8200"):
        _failure("backend: must publish host 8200 to target 8200", failures)

    backend_control = _service(model, "backend-control")
    control_env = _environment(backend_control)
    if _profiles(backend_control) != ["control-plane"]:
        _failure("backend-control: must be limited to control-plane profile", failures)
    _require_env("backend-control", control_env, "MINDSCAPE_BACKEND_ROLE", "control", failures)
    _require_env("backend-control", control_env, "DB_POOL_SIZE", "4", failures)
    _require_env("backend-control", control_env, "DB_MAX_OVERFLOW", "2", failures)
    _require_env_contains("backend-control", control_env, "DATABASE_URL_CORE", "@pgbouncer:6432/mindscape_core", failures)
    _require_env_contains("backend-control", control_env, "DATABASE_URL_CORE_SESSION", "@postgres:5432/mindscape_core", failures)
    for dependency in CORE_DEPENDENCIES:
        if _depends_condition(backend_control, dependency) != "service_healthy":
            _failure(f"backend-control: {dependency} dependency must be service_healthy", failures)
    if "8210/healthz" not in _healthcheck_text(backend_control):
        _failure("backend-control: healthcheck must probe 8210/healthz", failures)
    if not _has_port(backend_control, target=8210, published="8220"):
        _failure("backend-control: must publish host 8220 to target 8210", failures)

    frontend = _service(model, "frontend")
    if _profiles(frontend) != ["control-plane"]:
        _failure("frontend: must be limited to control-plane profile", failures)
    if _depends_condition(frontend, "backend-control") != "service_healthy":
        _failure("frontend: backend-control dependency must be service_healthy", failures)
    if _depends_condition(frontend, "backend"):
        _failure("frontend: must not depend on execution backend directly", failures)
    if "3000/healthz" not in _healthcheck_text(frontend):
        _failure("frontend: healthcheck must probe 3000/healthz", failures)
    if not _has_port(frontend, target=3000, published="8300"):
        _failure("frontend: must publish host 8300 to target 3000", failures)
    if not _has_readonly_volume(frontend, "/app/config"):
        _failure("frontend: must mount /app/config read-only for endpoint seed access", failures)
    return failures


def validate_data_plane(model: Mapping[str, Any], pgbouncer_config: PgBouncerConfig) -> list[str]:
    failures: list[str] = []
    postgres = _service(model, "postgres")
    if "pg_isready" not in _healthcheck_text(postgres):
        _failure("postgres: healthcheck must use pg_isready", failures)
    if not _has_port(postgres, target=5432, published="5433"):
        _failure("postgres: must publish host 5433 to target 5432", failures)
    pgbouncer = _service(model, "pgbouncer")
    if _depends_condition(pgbouncer, "postgres") != "service_healthy":
        _failure("pgbouncer: postgres dependency must be service_healthy", failures)
    if "6432" not in _healthcheck_text(pgbouncer):
        _failure("pgbouncer: healthcheck must probe port 6432", failures)
    if not _has_readonly_volume(pgbouncer, "/etc/pgbouncer/pgbouncer.ini"):
        _failure("pgbouncer: config volume must be read-only", failures)
    expected_pgbouncer = {
        "pool_mode": "transaction",
        "max_client_conn": "500",
        "default_pool_size": "30",
        "reserve_pool_size": "10",
        "server_reset_query": "DISCARD ALL",
    }
    for key, expected in expected_pgbouncer.items():
        actual = pgbouncer_config.pgbouncer.get(key)
        if actual != expected:
            _failure(f"pgbouncer.ini: expected {key}={expected!r}, got {actual!r}", failures)
    expected_databases = {
        "mindscape_core": ("postgres", "mindscape_core", ""),
        "mindscape_vectors": ("postgres", "mindscape_vectors", ""),
        "mindscape_core_readonly": ("postgres-replica", "mindscape_core", "10"),
        "mindscape_vectors_readonly": ("postgres-replica", "mindscape_vectors", "5"),
    }
    for name, (host, dbname, pool_size) in expected_databases.items():
        database = pgbouncer_config.databases.get(name) or {}
        if database.get("host") != host or database.get("dbname") != dbname:
            _failure(f"pgbouncer.ini: {name} must route to host={host}, dbname={dbname}", failures)
        if pool_size and database.get("pool_size") != pool_size:
            _failure(f"pgbouncer.ini: {name} must set pool_size={pool_size}", failures)
    replica = _service(model, "postgres-replica")
    if _profiles(replica) != ["ha"]:
        _failure("postgres-replica: must be limited to ha profile", failures)
    if _depends_condition(replica, "postgres") != "service_healthy":
        _failure("postgres-replica: postgres dependency must be service_healthy", failures)
    return failures


def validate_runner_pool(model: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    for service_name, expectations in RUNNER_EXPECTATIONS.items():
        runner = _service(model, service_name)
        if not runner:
            _failure(f"{service_name}: runner service missing", failures)
            continue
        env = _environment(runner)
        if expectations.get("compose_profile") and _profiles(runner) != [expectations["compose_profile"]]:
            _failure(f"{service_name}: expected profiles {[expectations['compose_profile']]}", failures)
        if not _healthcheck_disabled(runner):
            _failure(f"{service_name}: runner healthcheck must remain disabled", failures)
        if list(runner.get("entrypoint") or []) != ["python", "-m", "backend.app.runner.worker"]:
            _failure(f"{service_name}: entrypoint must stay on backend.app.runner.worker", failures)
        for dependency in RUNNER_DEPENDENCIES:
            if _depends_condition(runner, dependency) != "service_healthy":
                _failure(f"{service_name}: {dependency} dependency must be service_healthy", failures)
        _require_env(service_name, env, "LOCAL_CORE_RUNNER_PROFILE", expectations["profile"], failures)
        _require_env(service_name, env, "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS", expectations["accepted_partitions"], failures)
        _require_env(service_name, env, "LOCAL_CORE_RUNNER_MAX_INFLIGHT", expectations["max_inflight"], failures)
        _require_env(service_name, env, "DB_POOL_SIZE", expectations["pool_size"], failures)
        _require_env(service_name, env, "DB_MAX_OVERFLOW", expectations["max_overflow"], failures)
        if "maintenance_only" in expectations:
            _require_env(
                service_name,
                env,
                "LOCAL_CORE_RUNNER_MAINTENANCE_ONLY",
                expectations["maintenance_only"],
                failures,
            )
        if "startup_reconcile_enabled" in expectations:
            _require_env(
                service_name,
                env,
                "LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED",
                expectations["startup_reconcile_enabled"],
                failures,
            )
        _require_env_contains(service_name, env, "DATABASE_URL_CORE", "@pgbouncer:6432/mindscape_core", failures)
        _require_env_contains(service_name, env, "DATABASE_URL_CORE_SESSION", "@postgres:5432/mindscape_core", failures)
    return failures


def validate_optional_services(model: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    ocr = _service(model, "ocr-service")
    if _profiles(ocr) != ["ocr"]:
        _failure("ocr-service: must be limited to ocr profile", failures)
    if "8001/health" not in _healthcheck_text(ocr):
        _failure("ocr-service: healthcheck must probe 8001/health", failures)
    return failures


def validate_service_endpoint_seed(seed: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    expected_urls = {
        ("local_core.execution_api", "container_internal"): "http://backend:8200",
        ("local_core.control_api", "container_internal"): "http://backend-control:8210",
        ("local_core.control_api", "server_internal"): "http://backend-control:8210",
        ("local_core.web_console", "container_internal"): "http://frontend:3000",
        ("local_core.web_console", "browser_public"): "http://localhost:8300",
        ("local_core.media_proxy", "container_internal"): "http://media-proxy:8000",
        ("local_core.postgres_pool", "container_internal"): "postgresql://pgbouncer:6432",
        ("local_core.postgres_direct", "container_internal"): "postgresql://postgres:5432",
    }
    for (service_id, audience), expected in expected_urls.items():
        actual = _seed_url(seed, service_id, audience)
        if actual != expected:
            _failure(
                f"service-endpoints.seed.json: {service_id}/{audience} expected {expected!r}, got {actual!r}",
                failures,
            )
    return failures


def validate_profile_models(
    models: Mapping[str, Mapping[str, Any]],
    *,
    pgbouncer_config: PgBouncerConfig,
    service_endpoint_seed: Mapping[str, Any],
) -> list[str]:
    all_model = models.get("all-profiles", {})
    failures = validate_service_sets(models)
    failures.extend(validate_backend_planes(all_model))
    failures.extend(validate_data_plane(all_model, pgbouncer_config))
    failures.extend(validate_runner_pool(all_model))
    failures.extend(validate_optional_services(all_model))
    failures.extend(validate_service_endpoint_seed(service_endpoint_seed))
    return failures
