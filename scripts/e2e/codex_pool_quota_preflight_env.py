"""Environment and CLI compatibility helpers for Codex quota preflight."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


_MIN_SUPPORTED_CODEX_CLI_VERSION = "0.39.0"
_REQUIRED_CODEX_EXEC_FLAGS = ("--output-last-message", "--skip-git-repo-check")


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
