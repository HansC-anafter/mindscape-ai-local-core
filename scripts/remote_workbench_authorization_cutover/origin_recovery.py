"""Failure-closed recovery for dependents stopped during origin reconcile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .io import CutoverError, assert_private_file, write_private_json
from .resources import RedisResourceSampler, ResourceSnapshot


INFRASTRUCTURE_ORDER = ("postgres", "postgres-replica", "redis", "pgbouncer")
OPTIONAL_SERVICE_ORDER = (
    "ocr-service",
    "media-proxy",
    "xtts-service",
    "whisper-service",
)
APPLICATION_ORDER = ("backend", "backend-control", "frontend")


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
            "resource_before": {
                "totals": snapshot.totals,
                "inventory": list(snapshot.inventory),
                "runners": snapshot.runners,
            },
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
        "pre_active_services",
        "mutated_services",
        "stopped_dependents",
        "resource_before",
    }
    if not isinstance(state, dict) or set(state) != expected_keys:
        raise CutoverError("Origin reconcile state schema is invalid")
    if type(state["reconcile_completed"]) is not bool:
        raise CutoverError("Origin reconcile completion marker is invalid")
    if state["reconcile_completed"] is True:
        write_private_json(secure_dir / "origin-recovery-readback.json", state)
        return False
    lists = [
        state[key]
        for key in ("pre_active_services", "mutated_services", "stopped_dependents")
    ]
    if any(
        not isinstance(value, list) or not all(isinstance(item, str) for item in value)
        for value in lists
    ):
        raise CutoverError("Origin reconcile service inventory is invalid")
    resource_before = state["resource_before"]
    if not isinstance(resource_before, dict):
        raise CutoverError("Origin reconcile resource identity is invalid")
    try:
        before = RedisResourceSampler._validate(
            {
                "totals": resource_before["totals"],
                "inventory": resource_before["inventory"],
                "runners": {
                    **resource_before["runners"],
                    "malformed": 0,
                },
            }
        )
    except (KeyError, TypeError) as error:
        raise CutoverError("Origin reconcile resource identity is invalid") from error
    config = gate._compose_config(all_profiles=True)
    all_services = set(config["services"])
    if any(not set(value).issubset(all_services) for value in lists):
        raise CutoverError("Origin reconcile state names an unknown service")
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
    if not mutated.issubset(pre_active_services):
        raise CutoverError("Origin recovery contains a non-pre-active mutation")
    recovery = pre_active_services.intersection(mutated.union(stopped))
    runners = {name for name in recovery if name.startswith("runner")}
    if runners.intersection(mutated):
        raise CutoverError("Origin recovery cannot recreate a runner service")
    infrastructure = set(INFRASTRUCTURE_ORDER)
    application = set(APPLICATION_ORDER)
    optional = set(OPTIONAL_SERVICE_ORDER)
    unsupported = (
        recovery.difference(infrastructure)
        .difference(application)
        .difference(optional)
        .difference(runners)
    )
    if unsupported:
        raise CutoverError("Origin recovery contains an unsupported service")
    ordered = (
        [name for name in INFRASTRUCTURE_ORDER if name in recovery]
        + [name for name in OPTIONAL_SERVICE_ORDER if name in recovery]
        + [name for name in APPLICATION_ORDER if name in recovery]
        + sorted(runners)
    )
    for name in ordered:
        if name in mutated:
            gate.executor.run(
                gate.compose_command(
                    "up",
                    "-d",
                    "--force-recreate",
                    "--no-deps",
                    "--wait",
                    "--wait-timeout",
                    "300",
                    name,
                ),
                timeout_seconds=300.0,
            )
        else:
            gate.executor.run(
                gate.compose_command("start", name),
                timeout_seconds=180.0,
            )
        _evidence, reasons = gate._inspect_service(name, config["services"][name])
        if reasons:
            raise CutoverError("Recovered origin dependent is not healthy")
    after = RedisResourceSampler(gate.executor).capture()
    RedisResourceSampler.compare(before, after)
