"""Failure-closed recovery for dependents stopped during origin reconcile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import CutoverError, assert_private_file, write_private_json
from .resources import RedisResourceSampler, ResourceSnapshot


def persist_reconcile_state(
    gate: Any,
    *,
    secure_dir: Path,
    active_services: set[str],
    mutated_services: Sequence[str],
    stopped_dependents: Sequence[str],
) -> ResourceSnapshot:
    """Persist the exact pre-active service and runner-capacity identity."""

    snapshot = RedisResourceSampler(gate.executor).capture()
    write_private_json(
        secure_dir / "origin-reconcile-state.json",
        {
            "reconcile_completed": False,
            "pre_active_services": sorted(active_services),
            "mutated_services": sorted(mutated_services),
            "stopped_dependents": list(stopped_dependents),
            "runner_count": snapshot.runners["count"],
            "runner_capacity": snapshot.runners["capacity"],
        },
    )
    return snapshot


def mark_reconcile_completed(secure_dir: Path) -> None:
    path = secure_dir / "origin-reconcile-state.json"
    assert_private_file(path, max_bytes=32_768)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Origin reconcile state is malformed") from error
    if not isinstance(state, dict) or state.get("reconcile_completed") is not False:
        raise CutoverError("Origin reconcile completion transition is invalid")
    state["reconcile_completed"] = True
    write_private_json(path, state)


def recover_persisted_reconcile_state(gate: Any, secure_dir: Path) -> bool:
    """Recover a persisted interrupted reconcile during explicit backout."""

    path = secure_dir / "origin-reconcile-state.json"
    if not path.exists():
        return False
    assert_private_file(path, max_bytes=32_768)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Origin reconcile state is malformed") from error
    expected_keys = {
        "reconcile_completed",
        "pre_active_services", "mutated_services", "stopped_dependents",
        "runner_count", "runner_capacity",
    }
    if not isinstance(state, dict) or set(state) != expected_keys:
        raise CutoverError("Origin reconcile state schema is invalid")
    if type(state["reconcile_completed"]) is not bool:
        raise CutoverError("Origin reconcile completion marker is invalid")
    if state["reconcile_completed"] is True:
        write_private_json(secure_dir / "origin-recovery-readback.json", state)
        return False
    lists = [state[key] for key in (
        "pre_active_services", "mutated_services", "stopped_dependents"
    )]
    if any(not isinstance(value, list) or not all(isinstance(item, str) for item in value) for value in lists):
        raise CutoverError("Origin reconcile service inventory is invalid")
    if type(state["runner_count"]) is not int or type(state["runner_capacity"]) is not int:
        raise CutoverError("Origin reconcile runner identity is invalid")
    config = gate._compose_config(all_profiles=True)
    all_services = set(config["services"])
    if any(not set(value).issubset(all_services) for value in lists):
        raise CutoverError("Origin reconcile state names an unknown service")
    before = ResourceSnapshot(
        totals={"pending": 0, "processing": 0, "delayed": 0, "deadletter": 0},
        inventory=(),
        runners={
            "count": state["runner_count"],
            "capacity": state["runner_capacity"],
            "inflight": 0,
        },
    )
    recover_pre_active_services(
        gate,
        config=config,
        pre_active_services=set(state["pre_active_services"]),
        mutated_services=state["mutated_services"],
        stopped_dependents=state["stopped_dependents"],
        before=before,
    )
    state["reconcile_completed"] = True
    write_private_json(path, state)
    write_private_json(secure_dir / "origin-recovery-readback.json", state)
    return True


def recover_pre_active_services(
    gate: Any,
    *,
    config: Mapping[str, Any],
    pre_active_services: set[str],
    mutated_services: Sequence[str],
    stopped_dependents: Sequence[str],
    before: ResourceSnapshot,
) -> None:
    """Restore only the exact pre-active mutation set, then prove all health."""

    mutated = set(mutated_services)
    stopped = set(stopped_dependents)
    project = str(config.get("name") or "mindscape-ai-local-core")
    current = gate._active_services(project)
    unexpected = sorted(current.intersection(mutated.difference(pre_active_services)))
    if unexpected:
        gate.executor.run(gate.compose_command("stop", *unexpected), timeout_seconds=180.0)
    recovery = pre_active_services.intersection(mutated.union(stopped))
    runners = {name for name in recovery if name.startswith("runner")}
    infrastructure = {"postgres", "postgres-replica", "redis", "pgbouncer"}
    application = {"backend", "backend-control", "frontend"}
    ordered = [
        [name for name in ("postgres", "postgres-replica", "redis") if name in recovery],
        ["pgbouncer"] if "pgbouncer" in recovery else [],
        sorted(recovery.difference(infrastructure).difference(application).difference(runners)),
        [name for name in ("backend", "backend-control", "frontend") if name in recovery],
        sorted(runners),
    ]
    for group in ordered:
        if group:
            gate.executor.run(
                gate.compose_command(
                    "up", "-d", "--force-recreate", "--no-deps", *group
                ),
                timeout_seconds=300.0,
            )
    for name in sorted(pre_active_services):
        _evidence, reasons = gate._inspect_service(name, config["services"][name])
        if set(reasons).intersection({"container_missing", "not_running", "unhealthy"}):
            raise CutoverError("Recovered origin dependent is not healthy")
    after = RedisResourceSampler(gate.executor).capture()
    if (
        after.runners["count"] != before.runners["count"]
        or after.runners["capacity"] != before.runners["capacity"]
    ):
        raise CutoverError("Origin recovery changed runner count or capacity")
