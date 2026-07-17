"""Runner capacity collector that preserves the configured aggregate budget."""

from __future__ import annotations

from typing import Any, Callable


RunCommand = Callable[[list[str], float], dict[str, Any]]


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
        inspected = run_command(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .Config.Env}}{{println .}}{{end}}",
                name,
            ],
            timeout_seconds,
        )
        if not inspected.get("ok"):
            return {"ok": False, "error_code": "runner_inspect_unavailable"}
        value = None
        for line in inspected.get("stdout", "").splitlines():
            if line.startswith("LOCAL_CORE_RUNNER_MAX_INFLIGHT="):
                value = int(line.partition("=")[2])
                break
        if value is None:
            return {"ok": False, "error_code": "runner_capacity_missing"}
        rows.append({"container": name, "max_inflight": value})
        aggregate += value
    return {"ok": bool(rows), "aggregate_max_inflight": aggregate, "rows": rows}
