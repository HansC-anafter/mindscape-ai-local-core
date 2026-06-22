"""Compose render runner and report builder."""

from __future__ import annotations

import configparser
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contract import COMPOSE_FILE, PGBOUNCER_CONFIG, PROFILE_SETS, SERVICE_ENDPOINT_SEED
from .contract import PgBouncerConfig, parse_pgbouncer_config
from .rules import service_names, validate_profile_models


def render_compose_model(repo_root: Path, profiles: Sequence[str]) -> dict[str, Any]:
    command = ["docker", "compose", "-f", str(repo_root / COMPOSE_FILE)]
    for profile in profiles:
        command.extend(["--profile", profile])
    command.extend(["config", "--format", "json"])
    result = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("docker compose config did not return a JSON object")
    return data


def validate_repo(
    repo_root: Path,
    *,
    renderer: Callable[[Path, Sequence[str]], dict[str, Any]] = render_compose_model,
) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for profile_name, profiles in PROFILE_SETS.items():
        try:
            models[profile_name] = renderer(repo_root, profiles)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{profile_name}: docker compose render failed: {exc}")
            models[profile_name] = {"services": {}}

    try:
        pgbouncer_config = parse_pgbouncer_config(
            (repo_root / PGBOUNCER_CONFIG).read_text(encoding="utf-8")
        )
    except (OSError, configparser.Error) as exc:
        failures.append(f"{PGBOUNCER_CONFIG}: failed to read PgBouncer config: {exc}")
        pgbouncer_config = PgBouncerConfig(databases={}, pgbouncer={})
    try:
        service_endpoint_seed = json.loads(
            (repo_root / SERVICE_ENDPOINT_SEED).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"{SERVICE_ENDPOINT_SEED}: failed to read endpoint seed: {exc}")
        service_endpoint_seed = {}

    failures.extend(
        validate_profile_models(
            models,
            pgbouncer_config=pgbouncer_config,
            service_endpoint_seed=service_endpoint_seed,
        )
    )
    profile_services = {
        profile_name: sorted(service_names(model))
        for profile_name, model in models.items()
    }
    return {
        "ok": not failures,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "profile_services": profile_services,
        "failures": failures,
    }
