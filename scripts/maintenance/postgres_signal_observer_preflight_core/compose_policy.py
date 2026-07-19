"""Canonical observer Compose admission policy projection."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any, Callable, Protocol

from scripts.maintenance.postgres_signal_observer_core.artifact import (
    OBSERVER_ARTIFACT_POSTGRES_DOCKERFILE,
)


RunCommand = Callable[[list[str], float], dict[str, Any]]


class ComposePolicyConfig(Protocol):
    repo_root: Path
    timeout_seconds: float


def collect_observer_compose_policy(
    command: RunCommand,
    config: ComposePolicyConfig,
) -> dict[str, Any]:
    result = command(
        [
            "docker",
            "compose",
            "--project-directory",
            str(config.repo_root),
            "--profile",
            "runtime-db-observer",
            "config",
            "--format",
            "json",
        ],
        config.timeout_seconds,
    )
    if not result.get("ok"):
        return {"ok": False, "error_code": "observer_compose_config_unavailable"}
    try:
        service = json.loads(result.get("stdout") or "{}")["services"][
            "postgres-signal-observer"
        ]
        environment = service.get("environment") or {}
        volume_targets = sorted(
            str(volume.get("target") or "")
            for volume in service.get("volumes") or []
            if isinstance(volume, dict)
        )
        artifact_source = (
            config.repo_root.resolve() / OBSERVER_ARTIFACT_POSTGRES_DOCKERFILE
        )
        artifact_mounts = [
            volume
            for volume in service.get("volumes") or []
            if isinstance(volume, dict)
            and volume.get("target") == "/app/docker/postgres/Dockerfile"
        ]
        try:
            artifact_source_owned = bool(
                artifact_source.is_absolute()
                and not artifact_source.is_symlink()
                and stat.S_ISREG(artifact_source.lstat().st_mode)
                and artifact_source.resolve() == artifact_source
            )
        except OSError:
            artifact_source_owned = False
        artifact_mount_matches = bool(
            len(artifact_mounts) == 1
            and type(artifact_mounts[0].get("type")) is str
            and artifact_mounts[0]["type"] == "bind"
            and type(artifact_mounts[0].get("source")) is str
            and artifact_mounts[0]["source"] == str(artifact_source)
            and type(artifact_mounts[0].get("target")) is str
            and artifact_mounts[0]["target"]
            == "/app/docker/postgres/Dockerfile"
            and type(artifact_mounts[0].get("read_only")) is bool
            and artifact_mounts[0]["read_only"] is True
        )
        policy = {
            "profiles": service.get("profiles"),
            "read_only": service.get("read_only"),
            "privileged": bool(service.get("privileged", False)),
            "pid": service.get("pid"),
            "network_mode": service.get("network_mode"),
            "cap_add": service.get("cap_add"),
            "cap_drop": service.get("cap_drop"),
            "cpus": float(service.get("cpus") or 0),
            "mem_limit": int(service.get("mem_limit") or 0),
            "pids_limit": int(service.get("pids_limit") or 0),
            "volume_targets": volume_targets,
            "artifact_source_owned": artifact_source_owned,
            "artifact_mount_matches": artifact_mount_matches,
            "environment_keys": sorted(environment),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error_code": "observer_compose_config_invalid"}
    policy_sha256 = hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    expected = {
        "profiles": ["runtime-db-observer"],
        "read_only": True,
        "privileged": False,
        "pid": "host",
        "network_mode": "service:pgbouncer",
        "cap_add": ["SYS_ADMIN"],
        "cap_drop": ["ALL"],
        "cpus": 0.1,
        "mem_limit": 67_108_864,
        "pids_limit": 16,
        "volume_targets": [
            "/app/backend",
            "/app/data",
            "/app/docker/postgres/Dockerfile",
            "/app/scripts",
        ],
        "artifact_source_owned": True,
        "artifact_mount_matches": True,
    }
    policy_matches = bool(
        type(policy.get("read_only")) is bool
        and all(policy.get(key) == value for key, value in expected.items())
    )
    docker_socket_present = any("docker.sock" in target for target in volume_targets)
    return {
        "ok": policy_matches and not docker_socket_present,
        "policy_sha256": policy_sha256,
        "policy_matches": policy_matches,
        "docker_socket_present": docker_socket_present,
        "resource_budget": {
            "cpus": policy["cpus"],
            "mem_limit": policy["mem_limit"],
            "pids_limit": policy["pids_limit"],
        },
        "cap_add": policy["cap_add"],
        "cap_drop": policy["cap_drop"],
        "artifact_source_owned": artifact_source_owned,
        "artifact_mount_matches": artifact_mount_matches,
    }
