"""Runtime environment probes for PostgreSQL preflight."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_ENV_DEFAULT_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]+)\}")
SCRIPT_PATHS = {
    "backup_job": "scripts/local_runtime_backup_job.py",
    "backup_verify": "scripts/verify_local_runtime_backup.sh",
    "legacy_compaction": "scripts/maintenance/compact_legacy_task_workflow_results.py",
    "retention_prune": "backend/scripts/prune_tasks_retention.py",
}


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(value or 0)} B"


def _resolve_compose_env_value(value: Any) -> str:
    text = str(value or "")

    def _replace(match: re.Match[str]) -> str:
        env_value = os.getenv(match.group(1))
        return env_value if env_value not in (None, "") else match.group(2)

    return COMPOSE_ENV_DEFAULT_RE.sub(_replace, text)


def _service_environment(service: Mapping[str, Any]) -> dict[str, str]:
    raw = service.get("environment") or {}
    if isinstance(raw, Mapping):
        return {
            str(key): _resolve_compose_env_value(value)
            for key, value in raw.items()
        }
    if isinstance(raw, list):
        env: dict[str, str] = {}
        for item in raw:
            key, separator, value = str(item).partition("=")
            if separator:
                env[key] = _resolve_compose_env_value(value)
        return env
    return {}


def _postgres_role_count(env: Mapping[str, str]) -> int:
    roles = 0
    for role in ("CORE", "VECTOR"):
        has_role = any(
            key == f"DATABASE_URL_{role}" or key.startswith(f"POSTGRES_{role}_")
            for key in env
        )
        if has_role:
            roles += 1
    return max(roles, 1)


def _compose_file_candidates(path: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    project_root = os.getenv("LOCAL_CORE_PROJECT_ROOT")
    if project_root:
        candidates.append(Path(project_root) / "docker-compose.yml")
    candidates.extend(
        [
            REPO_ROOT / "docker-compose.yml",
            Path("/repo/docker-compose.yml"),
            Path("/app/docker-compose.yml"),
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        expanded = candidate.expanduser()
        if expanded not in unique:
            unique.append(expanded)
    return unique


def _compose_command(compose_file: Path | None) -> list[str]:
    selected_compose = next(
        (
            candidate
            for candidate in _compose_file_candidates(compose_file)
            if candidate.is_file()
        ),
        None,
    )
    command = ["docker", "compose"]
    if selected_compose is not None:
        command.extend(["-f", str(selected_compose)])
    return command


def pg_repack_tool_status(compose_file: Path | None) -> dict[str, Any]:
    local_binary = shutil.which("pg_repack")
    if local_binary:
        return {
            "pg_repack_binary": local_binary,
            "pg_repack_binary_source": "local_path",
            "pg_repack_command": [local_binary],
        }

    if not shutil.which("docker"):
        return {
            "pg_repack_binary": None,
            "pg_repack_binary_source": None,
            "pg_repack_probe_error": "docker_cli_missing",
        }

    command = _compose_command(compose_file) + [
        "exec",
        "-T",
        "postgres",
        "sh",
        "-lc",
        "command -v pg_repack",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except Exception as exc:
        return {
            "pg_repack_binary": None,
            "pg_repack_binary_source": None,
            "pg_repack_probe_error": str(exc),
        }

    binary = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if result.returncode == 0 and binary:
        return {
            "pg_repack_binary": binary,
            "pg_repack_binary_source": "compose_postgres_service",
            "pg_repack_command": _compose_command(compose_file)
            + ["exec", "-T", "postgres", "pg_repack"],
        }

    return {
        "pg_repack_binary": None,
        "pg_repack_binary_source": None,
        "pg_repack_probe_error": (result.stderr or result.stdout).strip(),
    }


def connection_budget(
    *,
    compose_file: Path | None,
    max_connections: str,
    activity: Mapping[str, Any],
    connection_reserve: int,
) -> dict[str, Any]:
    selected_compose = next(
        (
            candidate
            for candidate in _compose_file_candidates(compose_file)
            if candidate.is_file()
        ),
        None,
    )
    max_connection_count = _parse_int(max_connections)
    safe_limit = max(max_connection_count - connection_reserve, 0)
    active_connections = _parse_int(activity.get("total_connections"))
    budget = {
        "source": str(selected_compose) if selected_compose else None,
        "source_available": bool(selected_compose),
        "max_connections": max_connection_count,
        "connection_reserve": connection_reserve,
        "safe_connection_limit": safe_limit,
        "active_connections": active_connections,
        "configured_connection_budget": 0,
        "services": [],
    }
    if selected_compose is None:
        return budget

    try:
        import yaml
    except Exception as exc:
        budget["error"] = f"pyyaml_unavailable: {exc}"
        budget["source_available"] = False
        return budget

    try:
        payload = yaml.safe_load(selected_compose.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        budget["error"] = str(exc)
        budget["source_available"] = False
        return budget

    services = payload.get("services") if isinstance(payload, Mapping) else {}
    if not isinstance(services, Mapping):
        return budget

    service_budgets: list[dict[str, Any]] = []
    for name, service in services.items():
        if not isinstance(service, Mapping):
            continue
        env = _service_environment(service)
        if "DB_POOL_SIZE" not in env and "DB_MAX_OVERFLOW" not in env:
            continue
        pool_size = _parse_int(env.get("DB_POOL_SIZE"))
        max_overflow = _parse_int(env.get("DB_MAX_OVERFLOW"))
        role_count = _postgres_role_count(env)
        connection_count = (pool_size + max_overflow) * role_count
        service_budgets.append(
            {
                "service": str(name),
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "postgres_role_count": role_count,
                "connection_budget": connection_count,
            }
        )

    budget["services"] = service_budgets
    budget["configured_connection_budget"] = sum(
        item["connection_budget"] for item in service_budgets
    )
    return budget


def compose_runtime_readiness(compose_file: Path | None) -> dict[str, Any]:
    selected_compose = next(
        (
            candidate
            for candidate in _compose_file_candidates(compose_file)
            if candidate.is_file()
        ),
        None,
    )
    readiness: dict[str, Any] = {
        "source": str(selected_compose) if selected_compose else None,
        "source_available": bool(selected_compose),
        "pgbouncer_service_defined": False,
        "backend_uses_pgbouncer": False,
        "runner_uses_pgbouncer": False,
        "read_replica_service_defined": False,
        "wal_archive_volume_configured": False,
        "redis_aof_configured": False,
        "redis_persistence_volume_configured": False,
    }
    if selected_compose is None:
        return readiness

    try:
        import yaml
    except Exception as exc:
        readiness["error"] = f"pyyaml_unavailable: {exc}"
        readiness["source_available"] = False
        return readiness

    try:
        payload = yaml.safe_load(selected_compose.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        readiness["error"] = str(exc)
        readiness["source_available"] = False
        return readiness

    services = payload.get("services") if isinstance(payload, Mapping) else {}
    if not isinstance(services, Mapping):
        return readiness

    pgbouncer_service = services.get("pgbouncer")
    readiness["pgbouncer_service_defined"] = isinstance(pgbouncer_service, Mapping)
    readiness["read_replica_service_defined"] = isinstance(
        services.get("postgres-replica"),
        Mapping,
    )

    postgres_service = services.get("postgres")
    if isinstance(postgres_service, Mapping):
        volumes = [str(item) for item in postgres_service.get("volumes") or []]
        readiness["wal_archive_volume_configured"] = any(
            "wal_archive" in item or "postgres-wal-archive" in item
            for item in volumes
        )

    redis_service = services.get("redis")
    if isinstance(redis_service, Mapping):
        command = [str(item) for item in redis_service.get("command") or []]
        volumes = [str(item) for item in redis_service.get("volumes") or []]
        readiness["redis_aof_configured"] = (
            "--appendonly" in command and "yes" in command
        )
        readiness["redis_persistence_volume_configured"] = any(
            item.endswith(":/data") or ":/data:" in item for item in volumes
        )

    backend_service = services.get("backend")
    if isinstance(backend_service, Mapping):
        backend_env = _service_environment(backend_service)
        readiness["backend_uses_pgbouncer"] = (
            backend_env.get("POSTGRES_CORE_HOST") == "pgbouncer"
            and backend_env.get("POSTGRES_CORE_PORT") == "6432"
        )

    runner_env = payload.get("x-runner-environment")
    if isinstance(runner_env, Mapping):
        resolved_runner_env = {
            str(key): _resolve_compose_env_value(value)
            for key, value in runner_env.items()
        }
        readiness["runner_uses_pgbouncer"] = (
            resolved_runner_env.get("POSTGRES_CORE_HOST") == "pgbouncer"
            and resolved_runner_env.get("POSTGRES_CORE_PORT") == "6432"
        )

    return readiness


def _postgres_data_path_candidates(paths: Sequence[Path] | None) -> list[Path]:
    candidates: list[Path] = []
    candidates.extend(paths or [])
    env_path = os.getenv("LOCAL_CORE_POSTGRES_HOST_DIR")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            Path("/app/data/postgres"),
            REPO_ROOT / "data/postgres",
            Path("/var/lib/postgresql/data"),
        ]
    )
    unique: list[Path] = []
    for candidate in candidates:
        expanded = candidate.expanduser()
        if expanded not in unique:
            unique.append(expanded)
    return unique


def filesystem_capacity(
    *,
    postgres_data_paths: Sequence[Path] | None,
    relations: Sequence[Mapping[str, Any]],
    free_space_factor: float,
    free_space_reserve: int,
) -> dict[str, Any]:
    selected_path = next(
        (
            candidate
            for candidate in _postgres_data_path_candidates(postgres_data_paths)
            if candidate.exists()
        ),
        None,
    )
    largest_relation = max(
        relations,
        key=lambda row: _parse_int(row.get("total_bytes")),
        default={},
    )
    largest_relation_bytes = _parse_int(largest_relation.get("total_bytes"))
    required_free_bytes = (
        int(largest_relation_bytes * free_space_factor) + free_space_reserve
    )
    result: dict[str, Any] = {
        "source": str(selected_path) if selected_path else None,
        "source_available": bool(selected_path),
        "largest_relation": largest_relation.get("relname"),
        "largest_relation_bytes": largest_relation_bytes,
        "largest_relation_bytes_pretty": _format_bytes(largest_relation_bytes),
        "required_free_bytes": required_free_bytes,
        "required_free_bytes_pretty": _format_bytes(required_free_bytes),
        "free_space_factor": free_space_factor,
        "free_space_reserve": free_space_reserve,
    }
    if selected_path is None:
        return result

    usage = shutil.disk_usage(selected_path)
    result.update(
        {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_bytes_pretty": _format_bytes(usage.total),
            "used_bytes_pretty": _format_bytes(usage.used),
            "free_bytes_pretty": _format_bytes(usage.free),
        }
    )
    return result


def script_path_status() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "path": value,
            "exists": (REPO_ROOT / value).is_file(),
        }
        for key, value in SCRIPT_PATHS.items()
    }
