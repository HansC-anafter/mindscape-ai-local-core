#!/usr/bin/env python3
"""Read-only PostgreSQL runtime preflight report for physical reclaim gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT, BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


SCHEMA_VERSION = 1
DEFAULT_RELATIONS = ("tasks", "artifacts", "ig_accounts_flat")
REQUIRED_EXTENSIONS = ("pg_repack", "pg_stat_statements")
SCRIPT_PATHS = {
    "backup_job": "scripts/local_runtime_backup_job.py",
    "backup_verify": "scripts/verify_local_runtime_backup.sh",
    "legacy_compaction": "scripts/maintenance/compact_legacy_task_workflow_results.py",
    "retention_prune": "backend/scripts/prune_tasks_retention.py",
}
COMPOSE_ENV_DEFAULT_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]+)\}")
DEFAULT_CONNECTION_RESERVE = 20
DEFAULT_REPACK_FREE_SPACE_FACTOR = 1.2
DEFAULT_REPACK_FREE_SPACE_RESERVE = 1024 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


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


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _get_engine():
    from app.database.engine import engine_postgres_core

    return engine_postgres_core


def _mapping_one(
    conn,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = conn.execute(text(sql), dict(params or {})).mappings().first()
    return dict(row or {})


def _mapping_all(
    conn,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(text(sql), dict(params or {})).mappings()
    ]


def _show_setting(conn, name: str) -> str:
    row = conn.execute(text(f"SHOW {name}")).first()
    if not row:
        return ""
    return str(row[0] or "")


def _split_preload_libraries(value: str) -> set[str]:
    return {
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    }


def _relation_sizes(conn, relations: Iterable[str]) -> list[dict[str, Any]]:
    rows = _mapping_all(
        conn,
        """
        SELECT
            relname,
            pg_total_relation_size(relid)::bigint AS total_bytes,
            pg_relation_size(relid)::bigint AS heap_bytes,
            pg_indexes_size(relid)::bigint AS index_bytes,
            (
                pg_total_relation_size(relid)
                - pg_relation_size(relid)
                - pg_indexes_size(relid)
            )::bigint AS toast_bytes
        FROM pg_catalog.pg_statio_user_tables
        WHERE relname = ANY(:relations)
        ORDER BY pg_total_relation_size(relid) DESC
        """,
        {"relations": list(relations)},
    )
    for row in rows:
        for key in ("total_bytes", "heap_bytes", "index_bytes", "toast_bytes"):
            row[f"{key}_pretty"] = _format_bytes(row.get(key))
    return rows


def _hot_row_budget(
    conn,
    *,
    recent_hours: int,
    execution_context_budget: int,
    result_budget: int,
    params_budget: int,
) -> dict[str, Any]:
    return _mapping_one(
        conn,
        """
        SELECT
            COUNT(*)::bigint AS recent_rows,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(execution_context::text, ''))
                      > :execution_context_budget
            )::bigint AS execution_context_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(result::text, '')) > :result_budget
            )::bigint AS result_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(params::text, '')) > :params_budget
            )::bigint AS params_over_budget,
            COALESCE(MAX(octet_length(coalesce(execution_context::text, ''))), 0)::bigint
                AS max_execution_context_bytes,
            COALESCE(MAX(octet_length(coalesce(result::text, ''))), 0)::bigint
                AS max_result_bytes,
            COALESCE(MAX(octet_length(coalesce(params::text, ''))), 0)::bigint
                AS max_params_bytes
        FROM tasks
        WHERE created_at >= now() - (:recent_hours * interval '1 hour')
        """,
        {
            "recent_hours": recent_hours,
            "execution_context_budget": execution_context_budget,
            "result_budget": result_budget,
            "params_budget": params_budget,
        },
    )


def _activity(conn) -> dict[str, Any]:
    states = _mapping_all(
        conn,
        """
        SELECT state, COUNT(*)::bigint AS count
        FROM pg_stat_activity
        GROUP BY state
        ORDER BY state NULLS FIRST
        """,
    )
    state_counts = {
        str(row.get("state") or "backend"): int(row.get("count") or 0)
        for row in states
    }
    idle_in_transaction = int(state_counts.get("idle in transaction", 0))
    samples = _mapping_all(
        conn,
        """
        SELECT
            datname,
            application_name,
            state,
            wait_event_type,
            COUNT(*)::bigint AS count
        FROM pg_stat_activity
        GROUP BY datname, application_name, state, wait_event_type
        ORDER BY count DESC, state NULLS FIRST, application_name
        LIMIT 20
        """,
    )
    return {
        "state_counts": state_counts,
        "idle_in_transaction": idle_in_transaction,
        "total_connections": sum(state_counts.values()),
        "samples": samples,
    }


def _runner_workload(conn) -> dict[str, Any]:
    try:
        return _mapping_one(
            conn,
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'running')::bigint AS running_tasks,
                COUNT(*) FILTER (
                    WHERE status = 'running'
                      AND (
                        runner_id IS NOT NULL
                        OR execution_context->>'runner_id' IS NOT NULL
                      )
                )::bigint AS runner_owned_running_tasks,
                COUNT(*) FILTER (
                    WHERE status = 'pending'
                      AND (next_eligible_at IS NULL OR next_eligible_at <= now())
                )::bigint AS ready_pending_tasks,
                COUNT(DISTINCT COALESCE(runner_id, execution_context->>'runner_id'))
                    FILTER (
                        WHERE status = 'running'
                          AND COALESCE(runner_id, execution_context->>'runner_id')
                              IS NOT NULL
                    )::bigint AS active_runner_owners
            FROM tasks
            WHERE status IN ('running', 'pending')
            """,
        )
    except Exception as exc:
        return {"error": str(exc)}


def _installed_extensions(conn) -> set[str]:
    rows = _mapping_all(
        conn,
        """
        SELECT extname
        FROM pg_extension
        WHERE extname = ANY(:extensions)
        ORDER BY extname
        """,
        {"extensions": list(REQUIRED_EXTENSIONS)},
    )
    return {str(row["extname"]) for row in rows if row.get("extname")}


def _pg_stat_statements_top(conn, *, enabled: bool, limit: int) -> list[dict[str, Any]]:
    if not enabled:
        return []
    try:
        return _mapping_all(
            conn,
            """
            SELECT
                queryid,
                calls,
                total_exec_time,
                mean_exec_time,
                rows,
                left(query, 500) AS query
            FROM pg_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
    except Exception as exc:
        return [{"error": str(exc)}]


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


def _pg_repack_tool_status(compose_file: Path | None) -> dict[str, Any]:
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


def _connection_budget(
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


def _filesystem_capacity(
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


def _script_path_status() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "path": value,
            "exists": (REPO_ROOT / value).is_file(),
        }
        for key, value in SCRIPT_PATHS.items()
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_verification(backup_dir: Path | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": str(backup_dir) if backup_dir else None,
        "source_available": False,
        "verified": False,
        "verification_mode": "manifest_checksum",
        "errors": [],
    }
    if backup_dir is None:
        result["errors"].append("verified_backup_dir_required")
        return result

    backup_root = backup_dir.expanduser()
    result["source"] = str(backup_root)
    manifest_path = backup_root / "manifest.json"
    result["manifest_path"] = str(manifest_path)
    if not backup_root.is_dir():
        result["errors"].append("backup_dir_not_found")
        return result
    if not manifest_path.is_file():
        result["source_available"] = True
        result["errors"].append("manifest_missing")
        return result

    result["source_available"] = True
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result["errors"].append(f"manifest_invalid_json: {exc}")
        return result

    if not isinstance(manifest, dict):
        result["errors"].append("manifest_not_object")
        return result

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        result["errors"].append("manifest_artifacts_empty")
        artifacts = []

    checked_artifacts: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            result["errors"].append("artifact_not_object")
            continue
        rel_path = str(artifact.get("path") or "").strip()
        expected_sha = str(artifact.get("sha256") or "").strip()
        expected_size = _parse_int(artifact.get("bytes"), -1)
        if not rel_path:
            result["errors"].append("artifact_path_missing")
            continue
        artifact_path = backup_root / rel_path
        try:
            artifact_path.resolve().relative_to(backup_root.resolve())
        except Exception:
            result["errors"].append(f"artifact_path_outside_backup:{rel_path}")
            continue
        if not artifact_path.is_file():
            result["errors"].append(f"artifact_missing:{rel_path}")
            continue
        actual_size = artifact_path.stat().st_size
        if actual_size <= 0:
            result["errors"].append(f"artifact_empty:{rel_path}")
        if expected_size != actual_size:
            result["errors"].append(f"artifact_size_mismatch:{rel_path}")
        actual_sha = _file_sha256(artifact_path)
        if not expected_sha or expected_sha != actual_sha:
            result["errors"].append(f"artifact_sha256_mismatch:{rel_path}")
        checked_artifacts.append(
            {
                "path": rel_path,
                "bytes": actual_size,
                "sha256": actual_sha,
            }
        )

    options = manifest.get("options") if isinstance(manifest.get("options"), dict) else {}
    result.update(
        {
            "schema_version": manifest.get("schema_version"),
            "backup_name": manifest.get("backup_name"),
            "created_at": manifest.get("created_at"),
            "git_commit": manifest.get("git_commit"),
            "options": options,
            "artifact_count": len(checked_artifacts),
            "artifacts": checked_artifacts,
        }
    )
    result["verified"] = not result["errors"]
    return result


def _runner_claim_gate() -> dict[str, Any]:
    try:
        from backend.app.services.host_resources import get_runner_claim_gate

        gate = get_runner_claim_gate()
        if isinstance(gate, dict):
            return gate
        return {"error": "invalid_runner_claim_gate"}
    except Exception as exc:
        return {"error": str(exc)}


def _unavailable_database_report(
    args: argparse.Namespace,
    exc: Exception,
) -> dict[str, Any]:
    activity = {"error": "database_unavailable", "total_connections": 0}
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "mode": "read_only",
        "database": {
            "connectable": False,
            "connection_error": str(exc),
            "pg_is_in_recovery": None,
            "shared_preload_libraries": "",
            "max_connections": "",
        },
        "extensions": {
            "required": list(REQUIRED_EXTENSIONS),
            "installed": [],
        },
        "tools": _pg_repack_tool_status(args.compose_file),
        "script_paths": _script_path_status(),
        "backup_verification": _backup_verification(args.verified_backup_dir),
        "activity": activity,
        "connection_budget": _connection_budget(
            compose_file=args.compose_file,
            max_connections="",
            activity=activity,
            connection_reserve=args.connection_reserve,
        ),
        "relations": [],
        "filesystem": _filesystem_capacity(
            postgres_data_paths=args.postgres_data_path,
            relations=[],
            free_space_factor=args.repack_free_space_factor,
            free_space_reserve=args.repack_free_space_reserve,
        ),
        "runner_claim_gate": _runner_claim_gate(),
        "runner_workload": {"error": "database_unavailable"},
        "hot_row_budget": {
            "recent_hours": args.recent_hours,
            "limits": {
                "execution_context": args.execution_context_budget,
                "result": args.result_budget,
                "params": args.params_budget,
            },
            "sample": {},
        },
        "pg_stat_statements_top": [],
    }
    return evaluate_report(report)


def collect_report(args: argparse.Namespace) -> dict[str, Any]:
    engine = _get_engine()
    try:
        conn_ctx = engine.connect()
    except Exception as exc:
        return _unavailable_database_report(args, exc)

    with conn_ctx as conn:
        pg_is_in_recovery = bool(
            _mapping_one(conn, "SELECT pg_is_in_recovery() AS value").get("value")
        )
        shared_preload_libraries = _show_setting(conn, "shared_preload_libraries")
        max_connections = _show_setting(conn, "max_connections")
        installed_extensions = _installed_extensions(conn)
        pg_stat_statements_installed = "pg_stat_statements" in installed_extensions

        activity = _activity(conn)
        relations = _relation_sizes(conn, args.relation or DEFAULT_RELATIONS)

        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "mode": "read_only",
            "database": {
                "connectable": True,
                "pg_is_in_recovery": pg_is_in_recovery,
                "shared_preload_libraries": shared_preload_libraries,
                "max_connections": max_connections,
            },
            "extensions": {
                "required": list(REQUIRED_EXTENSIONS),
                "installed": sorted(installed_extensions),
            },
            "tools": _pg_repack_tool_status(args.compose_file),
            "script_paths": _script_path_status(),
            "backup_verification": _backup_verification(args.verified_backup_dir),
            "activity": activity,
            "connection_budget": _connection_budget(
                compose_file=args.compose_file,
                max_connections=max_connections,
                activity=activity,
                connection_reserve=args.connection_reserve,
            ),
            "relations": relations,
            "filesystem": _filesystem_capacity(
                postgres_data_paths=args.postgres_data_path,
                relations=relations,
                free_space_factor=args.repack_free_space_factor,
                free_space_reserve=args.repack_free_space_reserve,
            ),
            "runner_claim_gate": _runner_claim_gate(),
            "runner_workload": _runner_workload(conn),
            "hot_row_budget": {
                "recent_hours": args.recent_hours,
                "limits": {
                    "execution_context": args.execution_context_budget,
                    "result": args.result_budget,
                    "params": args.params_budget,
                },
                "sample": _hot_row_budget(
                    conn,
                    recent_hours=args.recent_hours,
                    execution_context_budget=args.execution_context_budget,
                    result_budget=args.result_budget,
                    params_budget=args.params_budget,
                ),
            },
            "pg_stat_statements_top": _pg_stat_statements_top(
                conn,
                enabled=pg_stat_statements_installed,
                limit=args.statement_limit,
            ),
        }

    return evaluate_report(report)


def _has_preload(report: Mapping[str, Any], library: str) -> bool:
    database = report.get("database") if isinstance(report.get("database"), dict) else {}
    preload = str(database.get("shared_preload_libraries") or "")
    return library in _split_preload_libraries(preload)


def evaluate_report(report: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    database = report.get("database") if isinstance(report.get("database"), dict) else {}
    if database.get("connectable") is False:
        blockers.append("database_unavailable")
    elif database.get("pg_is_in_recovery") is not False:
        blockers.append("database_in_recovery")

    extensions = (
        report.get("extensions") if isinstance(report.get("extensions"), dict) else {}
    )
    installed = set(extensions.get("installed") or [])
    if "pg_repack" not in installed:
        blockers.append("pg_repack_extension_missing")
    if "pg_stat_statements" not in installed:
        blockers.append("pg_stat_statements_extension_missing")
    if not _has_preload(report, "pg_stat_statements"):
        blockers.append("pg_stat_statements_not_preloaded")

    tools = report.get("tools") if isinstance(report.get("tools"), dict) else {}
    if not tools.get("pg_repack_binary"):
        blockers.append("pg_repack_binary_missing")

    script_paths = (
        report.get("script_paths")
        if isinstance(report.get("script_paths"), dict)
        else {}
    )
    for key, payload in script_paths.items():
        if not isinstance(payload, dict) or not payload.get("exists"):
            blockers.append(f"{key}_script_missing")

    backup_verification = (
        report.get("backup_verification")
        if isinstance(report.get("backup_verification"), dict)
        else {}
    )
    if not backup_verification.get("source"):
        blockers.append("verified_backup_missing")
    elif backup_verification.get("errors") or not backup_verification.get("verified"):
        blockers.append("verified_backup_invalid")
    else:
        backup_options = (
            backup_verification.get("options")
            if isinstance(backup_verification.get("options"), dict)
            else {}
        )
        if backup_options.get("skip_db") is True:
            blockers.append("verified_backup_skips_database")
        if backup_options.get("skip_files") is True:
            warnings.append("verified_backup_skips_files")

    activity = report.get("activity") if isinstance(report.get("activity"), dict) else {}
    idle_in_transaction = int(activity.get("idle_in_transaction") or 0)
    if idle_in_transaction > 0:
        blockers.append("idle_in_transaction_sessions_present")

    hot_row_budget = (
        report.get("hot_row_budget")
        if isinstance(report.get("hot_row_budget"), dict)
        else {}
    )
    sample = (
        hot_row_budget.get("sample")
        if isinstance(hot_row_budget.get("sample"), dict)
        else {}
    )
    over_budget = {
        "execution_context": int(sample.get("execution_context_over_budget") or 0),
        "result": int(sample.get("result_over_budget") or 0),
        "params": int(sample.get("params_over_budget") or 0),
    }
    if any(count > 0 for count in over_budget.values()):
        blockers.append("recent_hot_rows_over_budget")

    runner_workload = (
        report.get("runner_workload")
        if isinstance(report.get("runner_workload"), dict)
        else {}
    )
    if runner_workload.get("error"):
        blockers.append("runner_workload_unavailable")
    else:
        running_tasks = int(runner_workload.get("running_tasks") or 0)
        runner_owned_running_tasks = int(
            runner_workload.get("runner_owned_running_tasks") or 0
        )
        ready_pending_tasks = int(runner_workload.get("ready_pending_tasks") or 0)
        if running_tasks > 0 or runner_owned_running_tasks > 0:
            blockers.append("runner_workload_active")
        if ready_pending_tasks > 0:
            warnings.append("ready_pending_tasks_present")

    runner_claim_gate = (
        report.get("runner_claim_gate")
        if isinstance(report.get("runner_claim_gate"), dict)
        else {}
    )
    if runner_claim_gate.get("error"):
        blockers.append("runner_claim_gate_unavailable")
    elif runner_claim_gate.get("state") != "paused":
        blockers.append("runner_claim_gate_not_paused")
    elif not runner_claim_gate.get("persisted"):
        blockers.append("runner_claim_gate_not_persisted")

    connection_budget = (
        report.get("connection_budget")
        if isinstance(report.get("connection_budget"), dict)
        else {}
    )
    safe_connection_limit = int(connection_budget.get("safe_connection_limit") or 0)
    if not connection_budget.get("source_available"):
        warnings.append("connection_budget_unavailable")
    elif safe_connection_limit > 0:
        configured_budget = int(
            connection_budget.get("configured_connection_budget") or 0
        )
        active_connections = int(connection_budget.get("active_connections") or 0)
        if configured_budget > safe_connection_limit:
            blockers.append("configured_connection_budget_exceeds_safe_limit")
        if active_connections > safe_connection_limit:
            blockers.append("active_connections_exceed_safe_limit")

    filesystem = (
        report.get("filesystem") if isinstance(report.get("filesystem"), dict) else {}
    )
    if not filesystem.get("source_available"):
        blockers.append("postgres_data_path_unavailable")
    else:
        free_bytes = int(filesystem.get("free_bytes") or 0)
        required_free_bytes = int(filesystem.get("required_free_bytes") or 0)
        if free_bytes < required_free_bytes:
            blockers.append("insufficient_postgres_free_space")

    top_statements = report.get("pg_stat_statements_top")
    if not top_statements:
        warnings.append("pg_stat_statements_top_sql_unavailable")
    elif (
        isinstance(top_statements, list)
        and top_statements
        and top_statements[0].get("error")
    ):
        warnings.append("pg_stat_statements_top_sql_failed")

    evaluated = dict(report)
    evaluated["readiness"] = {
        "ready_for_physical_reclaim": not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }
    return evaluated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a read-only PostgreSQL runtime preflight report"
    )
    parser.add_argument(
        "--relation",
        action="append",
        default=None,
        help="Relation name to include in size sampling. Repeatable.",
    )
    parser.add_argument("--recent-hours", type=int, default=24)
    parser.add_argument("--execution-context-budget", type=int, default=512 * 1024)
    parser.add_argument("--result-budget", type=int, default=256 * 1024)
    parser.add_argument("--params-budget", type=int, default=512 * 1024)
    parser.add_argument("--statement-limit", type=int, default=10)
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument(
        "--verified-backup-dir",
        type=Path,
        help="Completed backup directory with manifest.json for reclaim readiness.",
    )
    parser.add_argument(
        "--connection-reserve",
        type=int,
        default=DEFAULT_CONNECTION_RESERVE,
    )
    parser.add_argument("--postgres-data-path", type=Path, action="append", default=None)
    parser.add_argument(
        "--repack-free-space-factor",
        type=float,
        default=DEFAULT_REPACK_FREE_SPACE_FACTOR,
    )
    parser.add_argument(
        "--repack-free-space-reserve",
        type=int,
        default=DEFAULT_REPACK_FREE_SPACE_RESERVE,
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 2 when blockers are present.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = collect_report(args)
    output = json.dumps(
        report,
        indent=2 if args.pretty else None,
        sort_keys=True,
        default=str,
    )
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(output + "\n", encoding="utf-8")
    print(output)
    if args.strict and report["readiness"]["blockers"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
