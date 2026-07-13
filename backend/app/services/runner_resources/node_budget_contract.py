"""Contracts and policy resolution for VM-wide browser byte admission."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol

from .node_memory import read_node_memory_snapshot

NODE_BUDGET_CONTEXT_KEY = "runner_node_budget_reservation"
NODE_BUDGET_ID = "docker_vm_browser_memory"


@dataclass(frozen=True)
class NodeBudgetPolicy:
    mode: str
    total_bytes: int
    vm_overhead_peak_bytes: int
    non_browser_peak_bytes: int
    browser_idle_peak_bytes: int
    allocatable_bytes: int
    fingerprint: str


@dataclass(frozen=True)
class NodeBudgetReservation:
    owner_id: str
    bytes: int
    revision: int
    expires_at_epoch: float
    policy_fingerprint: str
    resource_profile_fingerprint: str
    allocatable_bytes: int
    policy_mode: str
    reconciliation_evidence_fingerprint: str | None = None
    reconciled_from_bytes: int | None = None
    reconciled_at_epoch: float | None = None

    def to_context(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeBudgetAcquireResult:
    allow: bool
    reason: str | None
    reservation: NodeBudgetReservation | None
    reserved_bytes: int
    request_bytes: int
    policy: NodeBudgetPolicy


class NodeBudgetStore(Protocol):
    async def acquire(
        self,
        *,
        owner_id: str,
        request_bytes: int,
        policy: NodeBudgetPolicy,
        profile_fingerprint: str,
        ttl_seconds: int,
    ) -> NodeBudgetAcquireResult: ...

    async def renew(
        self,
        reservation: NodeBudgetReservation,
        *,
        ttl_seconds: int,
    ) -> bool: ...

    async def reconcile_down(
        self,
        reservation: NodeBudgetReservation,
        *,
        request_bytes: int,
        evidence_fingerprint: str,
    ) -> bool: ...

    async def release(self, reservation: NodeBudgetReservation) -> bool: ...

    async def snapshot(self) -> dict[str, Any]: ...


def _env_mb(name: str, source: Mapping[str, str]) -> int | None:
    raw = source.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def fingerprint_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def resource_profile_fingerprint(requirements: Any, request_bytes: int) -> str:
    payload = (
        requirements.to_dict()
        if hasattr(requirements, "to_dict")
        else dict(requirements or {})
    )
    payload["resolved_request_bytes"] = int(request_bytes)
    return fingerprint_payload(payload)


def resolve_node_budget_policy(
    node_snapshot: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> NodeBudgetPolicy | None:
    source = environ if environ is not None else os.environ
    try:
        total_bytes = int(node_snapshot.get("total_bytes") or 0)
        cgroup_limit_bytes = int(node_snapshot.get("cgroup_limit_bytes") or 0)
    except (TypeError, ValueError):
        return None
    if total_bytes <= 0:
        return None

    overhead_mb = _env_mb("LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB", source)
    non_browser_mb = _env_mb(
        "LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB",
        source,
    )
    browser_idle_mb = _env_mb(
        "LOCAL_CORE_RUNNER_NODE_BROWSER_IDLE_PEAK_MB",
        source,
    )
    if (
        overhead_mb is not None
        and non_browser_mb is not None
        and browser_idle_mb is not None
    ):
        mode = "calibrated"
        overhead_bytes = overhead_mb * 1024 * 1024
        non_browser_bytes = non_browser_mb * 1024 * 1024
        browser_idle_bytes = browser_idle_mb * 1024 * 1024
    elif 0 < cgroup_limit_bytes <= total_bytes:
        mode = "bootstrap_full_cgroup"
        overhead_bytes = total_bytes - cgroup_limit_bytes
        non_browser_bytes = 0
        browser_idle_bytes = 0
    else:
        return None

    allocatable = max(
        0,
        total_bytes - overhead_bytes - non_browser_bytes - browser_idle_bytes,
    )
    payload = {
        "mode": mode,
        "total_bytes": total_bytes,
        "vm_overhead_peak_bytes": overhead_bytes,
        "non_browser_peak_bytes": non_browser_bytes,
        "browser_idle_peak_bytes": browser_idle_bytes,
        "allocatable_bytes": allocatable,
    }
    return NodeBudgetPolicy(
        **payload,
        fingerprint=fingerprint_payload(payload),
    )


def resolve_browser_request_bytes(
    requirements: Any,
    node_snapshot: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[int, str] | None:
    source = environ if environ is not None else os.environ
    try:
        explicit_mb = int(getattr(requirements, "memory_mb", 0) or 0)
    except (TypeError, ValueError):
        explicit_mb = 0
    try:
        startup_mb = int(
            getattr(requirements, "browser_startup_memory_mb", 0) or 0
        )
    except (TypeError, ValueError):
        startup_mb = 0
    peak_mb = max(explicit_mb, startup_mb)
    if peak_mb > 0:
        request_source = (
            "playbook_peak_profile"
            if startup_mb > explicit_mb
            else "playbook_profile"
        )
        return peak_mb * 1024 * 1024, request_source

    observed_floor_mb = _env_mb(
        "LOCAL_CORE_RUNNER_BROWSER_UNMEASURED_RESERVATION_MB",
        source,
    )
    if observed_floor_mb and observed_floor_mb > 0:
        return (
            observed_floor_mb * 1024 * 1024,
            "observed_unmeasured_floor",
        )
    return None


def reservation_from_context(
    context: Mapping[str, Any] | None,
) -> NodeBudgetReservation | None:
    if not isinstance(context, Mapping):
        return None
    raw = context.get(NODE_BUDGET_CONTEXT_KEY)
    if not isinstance(raw, Mapping):
        return None
    try:
        return NodeBudgetReservation(
            owner_id=str(raw["owner_id"]),
            bytes=int(raw["bytes"]),
            revision=int(raw["revision"]),
            expires_at_epoch=float(raw["expires_at_epoch"]),
            policy_fingerprint=str(raw["policy_fingerprint"]),
            resource_profile_fingerprint=str(raw["resource_profile_fingerprint"]),
            allocatable_bytes=int(raw["allocatable_bytes"]),
            policy_mode=str(raw["policy_mode"]),
            reconciliation_evidence_fingerprint=(
                str(raw["reconciliation_evidence_fingerprint"])
                if raw.get("reconciliation_evidence_fingerprint")
                else None
            ),
            reconciled_from_bytes=(
                int(raw["reconciled_from_bytes"])
                if raw.get("reconciled_from_bytes") is not None
                else None
            ),
            reconciled_at_epoch=(
                float(raw["reconciled_at_epoch"])
                if raw.get("reconciled_at_epoch") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def current_node_memory_snapshot() -> dict[str, Any]:
    return read_node_memory_snapshot()
