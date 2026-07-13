"""Single ordered origin-reconcile transaction for the Phase06 topology gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .io import CutoverError, write_private_json
from .origin_recovery import (
    APPLICATION_ORDER,
    INFRASTRUCTURE_ORDER,
    OPTIONAL_SERVICE_ORDER,
    mark_reconcile_completed,
    persist_reconcile_state,
    recover_pre_active_services,
)


def _validate_reconcile_scope(
    gate: Any,
    *,
    drift: Mapping[str, Any],
    config: Mapping[str, Any],
    active_services: set[str],
) -> list[str]:
    services = sorted(str(name) for name in drift)
    if not set(services).issubset(active_services):
        raise CutoverError("Origin reconcile drift is not pre-active")
    if any(name.startswith("runner") for name in services):
        raise CutoverError("Runner drift blocks origin reconcile")
    for name, raw_reasons in drift.items():
        reasons = set(raw_reasons) if isinstance(raw_reasons, list) else set()
        expected = config["services"].get(name)
        if (
            not isinstance(expected, Mapping)
            or not gate._expected_bindings(expected)
            or "port_bindings" not in reasons
            or reasons.difference({"port_bindings", "lan_reachable"})
        ):
            raise CutoverError(
                "Origin reconcile only accepts pre-active published-port drift"
            )
    supported = (
        set(INFRASTRUCTURE_ORDER)
        | set(OPTIONAL_SERVICE_ORDER)
        | set(APPLICATION_ORDER)
    )
    if set(services).difference(supported):
        raise CutoverError("Origin reconcile drift names an unsupported service")
    return services


def _require_closed_result(gate: Any, secure_dir: Path, workspace_id: str) -> dict[str, Any]:
    result = gate.inspect(secure_dir, workspace_id)
    if result.get("drift") or result.get("lan_reachable_ports"):
        raise CutoverError("Canonical origin topology remains drifted after reconcile")
    write_private_json(secure_dir / "origin-topology-after.json", result)
    return result


def reconcile_origin(
    gate: Any,
    drift: Mapping[str, Any],
    *,
    secure_dir: Path,
    workspace_id: str,
) -> dict[str, Any]:
    """Recreate only pre-active binding drift, then prove a closed topology."""

    if not drift:
        return _require_closed_result(gate, secure_dir, workspace_id)
    config = gate._compose_config(all_profiles=True)
    active_services = gate._active_services(
        str(config.get("name") or "mindscape-ai-local-core")
    )
    services = _validate_reconcile_scope(
        gate,
        drift=drift,
        config=config,
        active_services=active_services,
    )
    stopped_dependents: list[str] = []
    if set(INFRASTRUCTURE_ORDER).intersection(services):
        stopped_dependents = [
            name for name in APPLICATION_ORDER if name in active_services
        ] + sorted(name for name in active_services if name.startswith("runner"))
    before = persist_reconcile_state(
        gate,
        secure_dir=secure_dir,
        active_services=active_services,
        mutated_services=services,
        stopped_dependents=stopped_dependents,
    )
    ordered_services = (
        [name for name in INFRASTRUCTURE_ORDER if name in services]
        + [name for name in OPTIONAL_SERVICE_ORDER if name in services]
        + [name for name in APPLICATION_ORDER if name in services]
    )
    try:
        if stopped_dependents:
            gate.executor.run(
                gate.compose_command("stop", *stopped_dependents),
                timeout_seconds=180.0,
            )
        for name in ordered_services:
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
            _evidence, reasons = gate._inspect_service(name, config["services"][name])
            if reasons:
                raise CutoverError("Reconciled origin service is not healthy")
        for name in (item for item in stopped_dependents if item not in services):
            gate.executor.run(
                gate.compose_command("start", name),
                timeout_seconds=180.0,
            )
            _evidence, reasons = gate._inspect_service(name, config["services"][name])
            if reasons:
                raise CutoverError("Restarted origin dependent is not healthy")
        result = _require_closed_result(gate, secure_dir, workspace_id)
        mark_reconcile_completed(secure_dir)
        return result
    except Exception as failure:
        try:
            recover_pre_active_services(
                gate,
                config=config,
                pre_active_services=active_services,
                mutated_services=services,
                stopped_dependents=stopped_dependents,
                before=before,
            )
        except Exception as recovery_error:
            raise CutoverError("Origin reconcile recovery failed closed") from recovery_error
        raise failure
