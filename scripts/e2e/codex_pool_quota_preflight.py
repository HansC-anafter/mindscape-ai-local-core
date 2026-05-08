#!/usr/bin/env python3
"""Probe Codex pool quota before expensive workspace E2E runs."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_dotenv_defaults(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _host_reachable_database_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.hostname != "postgres":
        return raw_url
    if os.getenv("PD_E2E_USE_DOCKER_NETWORK_DB_HOST", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return raw_url
    host_port = os.getenv("PD_E2E_POSTGRES_HOST_PORT", "5433").strip() or "5433"
    username = parsed.username or ""
    password = f":{parsed.password}" if parsed.password else ""
    auth = f"{username}{password}@" if username else ""
    netloc = f"{auth}localhost:{host_port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _load_local_backend_env() -> None:
    repo = _repo_root()
    _load_dotenv_defaults(repo / ".env")
    for key in ("DATABASE_URL_CORE", "DATABASE_URL_VECTOR", "DATABASE_URL"):
        value = os.environ.get(key)
        if value:
            os.environ[key] = _host_reachable_database_url(value)


def _bootstrap_imports() -> None:
    _load_local_backend_env()
    repo = _repo_root()
    for path in (repo, repo / "backend"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


def _env_keys(bundle: dict[str, Any]) -> list[str]:
    env = bundle.get("env")
    if not isinstance(env, dict):
        return []
    return sorted(str(key) for key in env.keys())


def _host_session_env_class(bundle: dict[str, Any]) -> str:
    env = bundle.get("env")
    if not isinstance(env, dict):
        return "none"
    if str(env.get("CODEX_HOME") or "").strip():
        return "codex_home"
    if str(env.get("HOME") or "").strip():
        return "plain_home"
    return "other"


_MIN_SUPPORTED_CODEX_CLI_VERSION = "0.39.0"
_REQUIRED_CODEX_EXEC_FLAGS = ("--output-last-message", "--skip-git-repo-check")


def _parse_version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.groups())


def _codex_cli_compatibility_check() -> dict[str, Any]:
    from backend.app.services.external_agents.bridge.codex_cli_runner import (
        resolve_codex_cli_binary,
    )

    binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
    evidence: dict[str, Any] = {
        "codex_cli_binary": binary,
        "codex_cli_version": None,
        "codex_cli_version_raw": "",
        "minimum_supported_codex_cli_version": _MIN_SUPPORTED_CODEX_CLI_VERSION,
        "required_flags_supported": {flag: False for flag in _REQUIRED_CODEX_EXEC_FLAGS},
        "codex_cli_compatible": False,
    }
    try:
        version_run = subprocess.run(
            [binary, "--version"],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        evidence["error"] = f"codex_cli_version_check_failed:{exc}"
        return evidence
    evidence["codex_cli_version_raw"] = (
        version_run.stdout or version_run.stderr or ""
    ).strip()
    if version_run.returncode != 0:
        evidence["error"] = "codex_cli_version_check_failed"
        evidence["codex_cli_version_returncode"] = version_run.returncode
        return evidence

    actual_version = _parse_version_tuple(evidence["codex_cli_version_raw"])
    minimum_version = _parse_version_tuple(_MIN_SUPPORTED_CODEX_CLI_VERSION)
    evidence["codex_cli_version"] = (
        ".".join(str(part) for part in actual_version) if actual_version else None
    )
    if not actual_version or actual_version < minimum_version:
        evidence["error"] = "codex_cli_version_incompatible"
        return evidence

    try:
        help_run = subprocess.run(
            [binary, "exec", "--help"],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        evidence["error"] = f"codex_cli_help_check_failed:{exc}"
        return evidence
    help_text = f"{help_run.stdout}\n{help_run.stderr}"
    evidence["codex_cli_exec_help_returncode"] = help_run.returncode
    evidence["required_flags_supported"] = {
        flag: flag in help_text for flag in _REQUIRED_CODEX_EXEC_FLAGS
    }
    if help_run.returncode != 0:
        evidence["error"] = "codex_cli_help_check_failed"
        return evidence
    if not all(evidence["required_flags_supported"].values()):
        evidence["error"] = "codex_cli_required_flags_unsupported"
        return evidence

    evidence["codex_cli_compatible"] = True
    return evidence


def _with_cli_evidence(
    result: dict[str, Any],
    cli_evidence: dict[str, Any],
) -> dict[str, Any]:
    result.update(cli_evidence)
    return result


def _normalized_required_login_email(args: argparse.Namespace) -> str:
    return str(
        args.required_login_email
        or os.environ.get("PD_E2E_REQUIRED_CODEX_LOGIN_EMAIL")
        or os.environ.get("CODEX_POOL_REQUIRED_LOGIN_EMAIL")
        or ""
    ).strip().lower()


async def _resolve_bundle(
    workspace_id: str,
    excluded_runtime_ids: set[str],
    excluded_quota_scope_keys: set[str],
) -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        resolve_codex_pool_runtime_bundle,
    )

    return await resolve_codex_pool_runtime_bundle(
        workspace_id=workspace_id,
        lease_owner_type="e2e_preflight",
        lease_owner_id=workspace_id,
        excluded_runtime_ids=excluded_runtime_ids,
        excluded_quota_scope_keys=excluded_quota_scope_keys,
        fail_closed_session_lease=False,
        record_runtime_lease=False,
    )


async def _runtime_pool_summary() -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        summarize_codex_pool_runtime_health,
    )

    return await summarize_codex_pool_runtime_health()


async def _report_runtime_fault(
    *,
    runtime_id: str,
    workspace_id: str,
    error_text: str,
) -> dict[str, str]:
    from backend.app.services.codex_pool_runtime_router import (
        report_codex_pool_runtime_fault,
    )
    from backend.app.services.codex_runtime_failure_classifier import (
        classify_codex_cli_runtime_failure,
    )

    classification = classify_codex_cli_runtime_failure(error_text)
    fault_kind = str(classification.get("fault_kind") or "runtime").strip()
    error_code = str(classification.get("error_code") or "runtime_error").strip()
    if fault_kind == "quota":
        await report_codex_pool_runtime_fault(
            runtime_id=runtime_id,
            fault_kind="quota",
            workspace_id=workspace_id,
            error_code=error_code,
            error_text=error_text,
        )
        return {"fault_kind": "quota", "error_code": error_code}
    if fault_kind == "auth":
        await report_codex_pool_runtime_fault(
            runtime_id=runtime_id,
            fault_kind="auth",
            workspace_id=workspace_id,
            error_code=error_code,
        )
        return {"fault_kind": "auth", "error_code": error_code}
    return {"fault_kind": "runtime", "error_code": error_code}


async def _report_runtime_success(*, runtime_id: str) -> dict[str, Any]:
    from backend.app.services.codex_pool_runtime_router import (
        report_codex_pool_runtime_success,
    )

    return await report_codex_pool_runtime_success(runtime_id=runtime_id)


def _direct_account_home_runtime_bundles(*, required_login_email: str = "") -> list[dict[str, Any]]:
    from backend.app.services.codex_pool_health import (
        is_pool_member_runtime_metadata,
        read_health_metadata,
    )
    from backend.app.services.codex_account_home_auth_source_service import (
        CodexAccountHomeAuthSourceService,
    )
    from backend.app.services.codex_pool_service import CODEX_POOL_GROUP, CodexPoolService

    service = CodexPoolService()
    db = service._get_db()
    RuntimeEnvironment = service._get_model()
    try:
        runtimes = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.pool_group == CODEX_POOL_GROUP,
                RuntimeEnvironment.pool_enabled.is_(True),
                RuntimeEnvironment.auth_type.in_(("host_session", "none")),
            )
            .all()
        )
        bundles: list[dict[str, Any]] = []
        for runtime in runtimes:
            metadata = dict(getattr(runtime, "extra_metadata", None) or {})
            auth_type = str(getattr(runtime, "auth_type", "") or "").strip()
            health = read_health_metadata(metadata, auth_type=auth_type)
            if str(health.get("seed_kind") or "").strip().lower() != "account_home":
                continue
            if not is_pool_member_runtime_metadata(metadata, auth_type=auth_type):
                continue
            login_email = str(metadata.get("login_email") or "").strip().lower()
            if required_login_email and login_email != required_login_email:
                continue
            env = {
                key: str(metadata.get(key) or "").strip()
                for key in (
                    "CODEX_HOME",
                    "HOME",
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                    "XDG_STATE_HOME",
                )
                if str(metadata.get(key) or "").strip()
            }
            codex_home = str(env.get("CODEX_HOME") or "").strip()
            if codex_home:
                metadata.update(
                    CodexAccountHomeAuthSourceService.metadata_for_codex_home(
                        codex_home,
                        metadata=metadata,
                    )
                )
            runtime_id = str(getattr(runtime, "id", "") or "").strip()
            account_key = str(metadata.get("account_key") or "").strip()
            quota_scope_key = (
                f"account:{account_key}"
                if account_key
                else str(metadata.get("quota_scope_key") or "").strip()
                or f"runtime:{runtime_id}"
            )
            try:
                auth_mtime_ns = (
                    Path(str(env.get("CODEX_HOME") or "")) / "auth.json"
                ).stat().st_mtime_ns
            except OSError:
                auth_mtime_ns = 0
            bundles.append(
                {
                    "selected_runtime_id": runtime_id,
                    "runtime_auth_type": auth_type,
                    "env": env,
                    "quota_scope_key": quota_scope_key,
                    "runtime_account_identity": {
                        "login_email": login_email or None,
                        "account_key": account_key or None,
                        "auth_account_id": str(
                            metadata.get("auth_account_id") or ""
                        ).strip()
                        or None,
                        "auth_chatgpt_user_id": str(
                            metadata.get("auth_chatgpt_user_id") or ""
                        ).strip()
                        or None,
                    },
                    "cooldown_until": str(getattr(runtime, "cooldown_until", "") or "")
                    or None,
                    "last_error_code": str(getattr(runtime, "last_error_code", "") or "")
                    or None,
                    "db_probe_state": str(metadata.get("probe_state") or "").strip()
                    or None,
                    "db_last_probe_error_code": str(
                        metadata.get("last_probe_error_code") or ""
                    ).strip()
                    or None,
                    "db_last_probe_success_at": str(
                        metadata.get("last_probe_success_at") or ""
                    ).strip()
                    or None,
                    "auth_mtime_ns": auth_mtime_ns,
                }
            )
        sorted_bundles = sorted(
            bundles,
            key=lambda item: (
                str(
                    (item.get("runtime_account_identity") or {}).get("login_email")
                    or ""
                ),
                -int(item.get("auth_mtime_ns") or 0),
                str(item.get("selected_runtime_id") or ""),
            ),
        )
        deduped: dict[str, dict[str, Any]] = {}
        for bundle in sorted_bundles:
            scope_key = str(bundle.get("quota_scope_key") or "").strip()
            deduped.setdefault(scope_key or str(bundle.get("selected_runtime_id")), bundle)
        return list(deduped.values())
    finally:
        db.close()


async def _probe_bundle(
    *,
    bundle: dict[str, Any],
    timeout_seconds: float,
    stall_timeout_seconds: float,
) -> dict[str, Any]:
    from backend.app.services.external_agents.bridge.codex_cli_runner import (
        resolve_codex_cli_binary,
        resolve_codex_cli_cwd,
        run_codex_cli_subprocess,
    )
    from backend.app.services.llm.core_llm import _merge_codex_env
    from backend.app.shared.llm_utils import extract_json_from_text

    binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
    cwd = resolve_codex_cli_cwd(os.environ.get("HOST_PROJECT_PATH", "").strip())
    with tempfile.NamedTemporaryFile(
        prefix="codex_pool_quota_probe_",
        suffix=".txt",
        delete=False,
    ) as tmp:
        last_message_path = tmp.name

    cmd = [
        binary,
        "-c",
        'model_reasoning_effort="low"',
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        last_message_path,
        'Return ONLY valid JSON: {"codex_pool_quota_probe": true}',
    ]
    try:
        result = await run_codex_cli_subprocess(
            cmd=cmd,
            cwd=cwd,
            env=_merge_codex_env(bundle.get("env")),
            last_message_path=last_message_path,
            execution_id=f"codex-pool-quota-probe-{uuid.uuid4()}",
            timeout=timeout_seconds,
            stall_timeout=stall_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        return {
            "success": False,
            "error": str(exc).strip() or "codex_cli quota probe timed out",
        }
    finally:
        try:
            os.unlink(last_message_path)
        except OSError:
            pass

    output_text = str(result.output_text or "").strip()
    parsed = extract_json_from_text(output_text)
    success = (
        result.returncode == 0
        and isinstance(parsed, dict)
        and parsed.get("codex_pool_quota_probe") is True
    )
    return {
        "success": success,
        "returncode": result.returncode,
        "output": output_text[:500],
        "error": (
            result.synthesized_error
            or result.combined_output
            or result.stderr_text
            or ""
        )[:1000],
    }


async def run_account_home_audit(args: argparse.Namespace) -> dict[str, Any]:
    required_login_email = _normalized_required_login_email(args)
    target_successes = max(1, int(args.target_successes or 1))
    cli_evidence = _codex_cli_compatibility_check()
    if not bool(cli_evidence.get("codex_cli_compatible")):
        return _with_cli_evidence(
            {
                "status": "blocked",
                "workspace_id": args.workspace_id,
                "target_successes": target_successes,
                "successful_runtime_count": 0,
                "successful_quota_scope_count": 0,
                "successful_runtime_ids": [],
                "successful_quota_scope_keys": [],
                "runtime_pool_summary": await _runtime_pool_summary(),
                "attempts": [],
                "audit_mode": "all_account_homes_ignore_cooldown",
            },
            cli_evidence,
        )

    bundles = _direct_account_home_runtime_bundles(
        required_login_email=required_login_email,
    )
    attempts: list[dict[str, Any]] = []
    successful_runtime_ids: list[str] = []
    successful_quota_scope_keys: list[str] = []
    successful_quota_scope_key_set: set[str] = set()
    for index, bundle in enumerate(bundles[: max(1, args.max_runtime_probes)]):
        runtime_id = str(bundle.get("selected_runtime_id") or "").strip()
        runtime_identity = bundle.get("runtime_account_identity")
        if not isinstance(runtime_identity, dict):
            runtime_identity = {}
        attempt: dict[str, Any] = {
            "attempt": index + 1,
            "selected_runtime_id": runtime_id or None,
            "runtime_account_identity": runtime_identity,
            "runtime_auth_type": bundle.get("runtime_auth_type"),
            "quota_scope_key": bundle.get("quota_scope_key"),
            "env_keys": _env_keys(bundle),
            "host_session_env_class": _host_session_env_class(bundle),
            "db_cooldown_until": bundle.get("cooldown_until"),
            "db_last_error_code": bundle.get("last_error_code"),
            "db_probe_state": bundle.get("db_probe_state"),
            "db_last_probe_error_code": bundle.get("db_last_probe_error_code"),
            "db_last_probe_success_at": bundle.get("db_last_probe_success_at"),
            "auth_mtime_ns": bundle.get("auth_mtime_ns"),
        }
        probe = await _probe_bundle(
            bundle=bundle,
            timeout_seconds=args.timeout_seconds,
            stall_timeout_seconds=args.stall_timeout_seconds,
        )
        attempt["probe"] = probe
        if probe.get("success"):
            attempt["status"] = "available"
            attempt["success_report"] = await _report_runtime_success(
                runtime_id=runtime_id,
            )
            successful_runtime_ids.append(runtime_id)
            quota_scope_key = str(bundle.get("quota_scope_key") or "").strip() or (
                f"runtime:{runtime_id}"
            )
            attempt["counted_quota_scope_key"] = quota_scope_key
            if quota_scope_key and quota_scope_key not in successful_quota_scope_key_set:
                successful_quota_scope_keys.append(quota_scope_key)
                successful_quota_scope_key_set.add(quota_scope_key)
        else:
            error_text = str(probe.get("error") or probe.get("output") or "").strip()
            fault_result = await _report_runtime_fault(
                runtime_id=runtime_id,
                workspace_id=args.workspace_id,
                error_text=error_text,
            )
            attempt.update({"status": "failed", **fault_result})
        attempts.append(attempt)

    final_status = (
        "available" if len(successful_quota_scope_key_set) >= target_successes else "failed"
    )
    return _with_cli_evidence(
        {
            "status": final_status,
            "workspace_id": args.workspace_id,
            "target_successes": target_successes,
            "successful_runtime_count": len(successful_runtime_ids),
            "successful_quota_scope_count": len(successful_quota_scope_key_set),
            "successful_runtime_ids": successful_runtime_ids,
            "successful_quota_scope_keys": successful_quota_scope_keys,
            "runtime_pool_summary": await _runtime_pool_summary(),
            "attempts": attempts,
            "audit_mode": "all_account_homes_ignore_cooldown",
            "audited_runtime_count": len(attempts),
        },
        cli_evidence,
    )


async def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    if bool(getattr(args, "audit_all_account_homes", False)):
        return await run_account_home_audit(args)

    excluded_runtime_ids: set[str] = {
        str(runtime_id or "").strip()
        for runtime_id in (args.exclude_runtime_id or [])
        if str(runtime_id or "").strip()
    }
    target_successes = max(1, int(args.target_successes or 1))
    cli_evidence = _codex_cli_compatibility_check()
    if not bool(cli_evidence.get("codex_cli_compatible")):
        return _with_cli_evidence(
            {
                "status": "blocked",
                "workspace_id": args.workspace_id,
                "target_successes": target_successes,
                "successful_runtime_count": 0,
                "successful_quota_scope_count": 0,
                "successful_runtime_ids": [],
                "successful_quota_scope_keys": [],
                "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                "runtime_pool_summary": await _runtime_pool_summary(),
                "attempts": [],
            },
            cli_evidence,
        )
    attempts: list[dict[str, Any]] = []
    successful_runtime_ids: list[str] = []
    successful_quota_scope_keys: list[str] = []
    successful_quota_scope_key_set: set[str] = set()
    excluded_quota_scope_keys: set[str] = set()
    for index in range(max(1, args.max_runtime_probes)):
        bundle = await _resolve_bundle(
            args.workspace_id,
            excluded_runtime_ids,
            excluded_quota_scope_keys,
        )
        pool_summary = await _runtime_pool_summary()
        pool_error = str(bundle.get("error") or bundle.get("warning") or "").strip()
        runtime_id = str(bundle.get("selected_runtime_id") or "").strip()
        runtime_identity = bundle.get("runtime_account_identity")
        if not isinstance(runtime_identity, dict):
            runtime_identity = {}
        attempt: dict[str, Any] = {
            "attempt": index + 1,
            "selected_runtime_id": runtime_id or None,
            "runtime_account_identity": runtime_identity,
            "preferred_runtime_id": bundle.get("preferred_runtime_id"),
            "auth_mode": bundle.get("auth_mode"),
            "runtime_auth_type": bundle.get("runtime_auth_type"),
            "available_runtime_count": bundle.get("available_runtime_count"),
            "available_quota_scope_count": bundle.get("available_quota_scope_count"),
            "quota_scope_key": bundle.get("quota_scope_key"),
            "env_keys": _env_keys(bundle),
            "host_session_env_class": _host_session_env_class(bundle),
            "policy_mode": bundle.get("policy_mode"),
            "requested_workspace_id": bundle.get("requested_workspace_id"),
            "effective_workspace_id": bundle.get("effective_workspace_id"),
            "auth_workspace_id": bundle.get("auth_workspace_id"),
            "source_workspace_id": bundle.get("source_workspace_id"),
            "selection_reason": bundle.get("selection_reason"),
            "selection_trace": bundle.get("selection_trace") or [],
            "admission": bundle.get("admission"),
            "runtime_pool_summary": pool_summary,
        }
        if pool_error:
            attempt.update({"status": "blocked", "error": pool_error})
            attempts.append(attempt)
            return _with_cli_evidence(
                {
                    "status": "blocked",
                    "workspace_id": args.workspace_id,
                    "target_successes": target_successes,
                    "successful_runtime_count": len(successful_runtime_ids),
                    "successful_quota_scope_count": len(successful_quota_scope_key_set),
                    "successful_runtime_ids": successful_runtime_ids,
                    "successful_quota_scope_keys": successful_quota_scope_keys,
                    "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                    "runtime_pool_summary": pool_summary,
                    "attempts": attempts,
                },
                cli_evidence,
            )
        if not runtime_id:
            attempt.update({"status": "blocked", "error": "missing selected_runtime_id"})
            attempts.append(attempt)
            return _with_cli_evidence(
                {
                    "status": "blocked",
                    "workspace_id": args.workspace_id,
                    "target_successes": target_successes,
                    "successful_runtime_count": len(successful_runtime_ids),
                    "successful_quota_scope_count": len(successful_quota_scope_key_set),
                    "successful_runtime_ids": successful_runtime_ids,
                    "successful_quota_scope_keys": successful_quota_scope_keys,
                    "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                    "runtime_pool_summary": pool_summary,
                    "attempts": attempts,
                },
                cli_evidence,
            )

        required_login_email = _normalized_required_login_email(args)
        if required_login_email:
            selected_login_email = str(
                runtime_identity.get("login_email") or ""
            ).strip().lower()
            attempt["required_login_email"] = required_login_email
            if selected_login_email != required_login_email:
                attempt.update(
                    {
                        "status": "identity_mismatch",
                        "error": "selected Codex runtime login email does not match required_login_email",
                        "selected_login_email": selected_login_email or None,
                    }
                )
                attempts.append(attempt)
                excluded_runtime_ids.add(runtime_id)
                continue

        probe = await _probe_bundle(
            bundle=bundle,
            timeout_seconds=args.timeout_seconds,
            stall_timeout_seconds=args.stall_timeout_seconds,
        )
        attempt["probe"] = probe
        if probe.get("success"):
            attempt["status"] = "available"
            attempt["success_report"] = await _report_runtime_success(
                runtime_id=runtime_id,
            )
            attempts.append(attempt)
            successful_runtime_ids.append(runtime_id)
            quota_scope_key = str(bundle.get("quota_scope_key") or "").strip() or (
                f"runtime:{runtime_id}"
            )
            attempt["counted_quota_scope_key"] = quota_scope_key
            if quota_scope_key and quota_scope_key not in successful_quota_scope_key_set:
                successful_quota_scope_keys.append(quota_scope_key)
                successful_quota_scope_key_set.add(quota_scope_key)
                excluded_quota_scope_keys.add(quota_scope_key)
            excluded_runtime_ids.add(runtime_id)
            if (
                len(successful_quota_scope_key_set) >= target_successes
                and not args.continue_after_success
            ):
                return _with_cli_evidence(
                    {
                        "status": "available",
                        "workspace_id": args.workspace_id,
                        "target_successes": target_successes,
                        "successful_runtime_count": len(successful_runtime_ids),
                        "successful_quota_scope_count": len(successful_quota_scope_key_set),
                        "successful_runtime_ids": successful_runtime_ids,
                        "successful_quota_scope_keys": successful_quota_scope_keys,
                        "selected_runtime_id": runtime_id,
                        "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
                        "runtime_pool_summary": pool_summary,
                        "attempts": attempts,
                    },
                    cli_evidence,
                )
            continue

        error_text = str(probe.get("error") or probe.get("output") or "").strip()
        fault_result = await _report_runtime_fault(
            runtime_id=runtime_id,
            workspace_id=args.workspace_id,
            error_text=error_text,
        )
        attempt.update({"status": "failed", **fault_result})
        attempts.append(attempt)
        excluded_runtime_ids.add(runtime_id)

    final_status = (
        "available" if len(successful_quota_scope_key_set) >= target_successes else "failed"
    )
    return _with_cli_evidence(
        {
            "status": final_status,
            "workspace_id": args.workspace_id,
            "target_successes": target_successes,
            "successful_runtime_count": len(successful_runtime_ids),
            "successful_quota_scope_count": len(successful_quota_scope_key_set),
            "successful_runtime_ids": successful_runtime_ids,
            "successful_quota_scope_keys": successful_quota_scope_keys,
            "initial_excluded_runtime_ids": sorted(args.exclude_runtime_id or []),
            "runtime_pool_summary": await _runtime_pool_summary(),
            "attempts": attempts,
        },
        cli_evidence,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Codex pool quota before running expensive E2E work.",
    )
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--max-runtime-probes", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--stall-timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--required-login-email",
        default="",
        help="Require the selected Codex runtime to expose this login email.",
    )
    parser.add_argument(
        "--exclude-runtime-id",
        action="append",
        default=[],
        help="Exclude a runtime before the first probe; repeat to simulate prior pool failures.",
    )
    parser.add_argument(
        "--target-successes",
        type=int,
        default=1,
        help="Require this many successful Codex CLI quota probes before returning available.",
    )
    parser.add_argument(
        "--continue-after-success",
        action="store_true",
        help="Continue probing until max-runtime-probes even after target-successes is reached.",
    )
    parser.add_argument(
        "--audit-all-account-homes",
        action="store_true",
        help=(
            "Probe every pool-enabled account-home runtime directly, ignoring DB cooldown "
            "and resolver admission. Use for external true/false audits, not normal scheduling."
        ),
    )
    parser.add_argument(
        "--compact-output",
        action="store_true",
        help="Print only per-attempt probe evidence and aggregate counts.",
    )
    return parser.parse_args()


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    attempts = result.get("attempts")
    if not isinstance(attempts, list):
        attempts = []

    compact_attempts: list[dict[str, Any]] = []
    failure_counts: dict[str, int] = {}
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        identity = attempt.get("runtime_account_identity")
        if not isinstance(identity, dict):
            identity = {}
        probe = attempt.get("probe")
        if not isinstance(probe, dict):
            probe = {}
        error_code = str(attempt.get("error_code") or "").strip()
        fault_kind = str(attempt.get("fault_kind") or "").strip()
        status = str(attempt.get("status") or "").strip()
        if error_code:
            failure_counts[error_code] = failure_counts.get(error_code, 0) + 1
        compact_attempts.append(
            {
                "attempt": attempt.get("attempt"),
                "status": status,
                "runtime_id": attempt.get("selected_runtime_id"),
                "login_email": identity.get("login_email"),
                "account_key": identity.get("account_key"),
                "quota_scope_key": attempt.get("quota_scope_key"),
                "counted_quota_scope_key": attempt.get("counted_quota_scope_key"),
                "db_cooldown_until": attempt.get("db_cooldown_until"),
                "db_last_error_code": attempt.get("db_last_error_code"),
                "db_probe_state": attempt.get("db_probe_state"),
                "db_last_probe_error_code": attempt.get("db_last_probe_error_code"),
                "db_last_probe_success_at": attempt.get("db_last_probe_success_at"),
                "auth_mtime_ns": attempt.get("auth_mtime_ns"),
                "fault_kind": fault_kind or None,
                "error_code": error_code or None,
                "probe_success": probe.get("success"),
                "probe_returncode": probe.get("returncode"),
                "probe_error": str(probe.get("error") or "")[:300] or None,
                "probe_output": str(probe.get("output") or "")[:200] or None,
            }
        )

    pool_summary = result.get("runtime_pool_summary")
    if not isinstance(pool_summary, dict):
        pool_summary = {}

    return {
        "status": result.get("status"),
        "workspace_id": result.get("workspace_id"),
        "target_successes": result.get("target_successes"),
        "successful_runtime_count": result.get("successful_runtime_count"),
        "successful_quota_scope_count": result.get("successful_quota_scope_count"),
        "successful_runtime_ids": result.get("successful_runtime_ids"),
        "successful_quota_scope_keys": result.get("successful_quota_scope_keys"),
        "codex_cli_binary": result.get("codex_cli_binary"),
        "codex_cli_version": result.get("codex_cli_version"),
        "minimum_supported_codex_cli_version": result.get(
            "minimum_supported_codex_cli_version"
        ),
        "required_flags_supported": result.get("required_flags_supported"),
        "codex_cli_compatible": result.get("codex_cli_compatible"),
        "attempt_count": len(compact_attempts),
        "failure_counts": failure_counts,
        "pool_summary": {
            "pool_enabled_runtime_count": pool_summary.get("pool_enabled_runtime_count"),
            "runnable_runtime_count": pool_summary.get("runnable_runtime_count"),
            "probe_available_runtime_count": pool_summary.get(
                "probe_available_runtime_count"
            ),
            "active_cooldown_count": pool_summary.get("active_cooldown_count"),
            "probe_state_counts": pool_summary.get("probe_state_counts"),
            "failure_counts": pool_summary.get("failure_counts"),
            "next_cooldown_until": pool_summary.get("next_cooldown_until"),
        },
        "audit_mode": result.get("audit_mode"),
        "audited_runtime_count": result.get("audited_runtime_count"),
        "attempts": compact_attempts,
    }


def main() -> int:
    _bootstrap_imports()
    args = parse_args()
    result = asyncio.run(run_preflight(args))
    if args.compact_output:
        result = _compact_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
