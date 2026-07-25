"""Runner capacity collector that preserves the configured aggregate budget."""

from __future__ import annotations

from typing import Any, Callable


RunCommand = Callable[[list[str], float], dict[str, Any]]

_RUNNER_ENV_KEYS = {
    "max_inflight": "LOCAL_CORE_RUNNER_MAX_INFLIGHT",
    "profile": "LOCAL_CORE_RUNNER_PROFILE",
    "accepted_partitions": "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS",
    "accepted_resource_classes": "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES",
}


def _read_exact_runner_env(
    run_command: RunCommand,
    container: str,
    key: str,
    timeout_seconds: float,
) -> str | None:
    result = run_command(
        ["docker", "exec", container, "printenv", key],
        timeout_seconds,
    )
    if not result.get("ok"):
        return None
    value = str(result.get("stdout") or "").strip()
    return value or None


def collect_runner_capacity(
    run_command: RunCommand,
    timeout_seconds: float,
) -> dict[str, Any]:
    listed = run_command(
        [
            "docker",
            "ps",
            "--filter",
            "name=mindscape-ai-local-core-runner",
            "--format",
            "{{.Names}}",
        ],
        timeout_seconds,
    )
    if not listed.get("ok"):
        return {"ok": False, "error_code": "runner_list_unavailable"}
    rows = []
    aggregate = 0
    for name in sorted(filter(None, listed.get("stdout", "").splitlines())):
        env = {
            field: _read_exact_runner_env(
                run_command,
                name,
                key,
                timeout_seconds,
            )
            for field, key in _RUNNER_ENV_KEYS.items()
        }
        if env["max_inflight"] is None:
            return {"ok": False, "error_code": "runner_capacity_missing"}
        if (
            env["profile"] is None
            or env["accepted_partitions"] is None
            or env["accepted_resource_classes"] is None
        ):
            return {"ok": False, "error_code": "runner_lane_identity_missing"}
        try:
            max_inflight = int(env["max_inflight"])
        except (TypeError, ValueError):
            return {"ok": False, "error_code": "runner_capacity_invalid"}
        rows.append(
            {
                "container": name,
                "max_inflight": max_inflight,
                "profile": env["profile"],
                "accepted_partitions": env["accepted_partitions"],
                "accepted_resource_classes": env["accepted_resource_classes"],
            }
        )
        aggregate += max_inflight
    return {"ok": bool(rows), "aggregate_max_inflight": aggregate, "rows": rows}
