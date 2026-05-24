"""Canonical scheduler contracts for host resource governance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResourceDemand:
    memory_mb: int = 0
    cpu_weight: int = 1
    exclusive_groups: tuple[str, ...] = ()
    vision_lane: str | None = None
    llm_lane: str | None = None
    browser_contexts: int = 0
    db_write_budget: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResourceFlavor:
    flavor_id: str
    source: str = "local"
    runtime_id: str | None = None
    transport: str | None = None
    site_key: str | None = None
    device_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdmissionDecisionEnvelope:
    allow: bool
    decision: str
    reason: str | None = None
    source: str = "host_resource_governance"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteIntent:
    target_lane: str | None = None
    resource_flavor: str | None = None
    resource_groups: tuple[str, ...] = ()
    priority_class: str = "default"
    drain_policy: str = "drain_after_current"
    preemption_policy: str = "never"
    resume_policy: str = "auto_restore_previous"
    requested_by: str = "host_resource_governance"

    def to_route_request(self) -> dict[str, Any]:
        return {
            "target_lane": self.target_lane,
            "resource_flavor": self.resource_flavor,
            "resource_groups": list(self.resource_groups),
            "priority_class": self.priority_class,
            "drain_policy": self.drain_policy,
            "preemption_policy": self.preemption_policy,
            "resume_policy": self.resume_policy,
            "requested_by": self.requested_by,
        }


@dataclass(frozen=True)
class RouteIdentityProjection:
    task_id: str
    route_identity: dict[str, Any]
    pack_id: str | None = None
    playbook_code: str | None = None
    task_type: str | None = None
    workspace_id: str | None = None
    queue_shard: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ControlPlanePressure:
    state: str
    memory_mb: float = 0
    process_count: int = 0
    primary_blockers: tuple[dict[str, Any], ...] = ()
    recommended_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple | set):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def from_resource_requirements(requirements: Any) -> ResourceDemand:
    groups: list[str] = []
    for lane in (
        getattr(requirements, "vision_lane", None),
        getattr(requirements, "llm_lane", None),
    ):
        if lane:
            groups.append(str(lane))
    return ResourceDemand(
        memory_mb=max(0, int(getattr(requirements, "memory_mb", 0) or 0)),
        cpu_weight=max(0, int(getattr(requirements, "cpu_weight", 1) or 1)),
        exclusive_groups=tuple(groups),
        vision_lane=getattr(requirements, "vision_lane", None),
        llm_lane=getattr(requirements, "llm_lane", None),
        browser_contexts=max(0, int(getattr(requirements, "browser_contexts", 0) or 0)),
        db_write_budget=max(0, int(getattr(requirements, "db_write_budget", 0) or 0)),
    )


def from_decision(
    decision: Any,
    *,
    source: str,
    allow_attr: str = "allow",
) -> AdmissionDecisionEnvelope:
    allow = bool(getattr(decision, allow_attr, False))
    if hasattr(decision, "allowed"):
        allow = bool(getattr(decision, "allowed"))
    return AdmissionDecisionEnvelope(
        allow=allow,
        decision=str(getattr(decision, "decision", None) or ("allow" if allow else "defer")),
        reason=getattr(decision, "reason", None),
        source=source,
        payload=dict(getattr(decision, "payload", None) or getattr(decision, "blocked_payload", None) or {}),
    )


def resource_flavor_from_runtime_binding(binding: Any) -> ResourceFlavor:
    runtime_id = getattr(binding, "runtime_id", None)
    transport = getattr(binding, "transport", None)
    site_key = getattr(binding, "site_key", None)
    device_id = getattr(binding, "device_id", None)
    if runtime_id:
        if transport and str(transport).strip() not in {"docker_local", "local"}:
            flavor_id = f"external.{transport}.{runtime_id}"
            source = "external"
        elif site_key:
            flavor_id = f"vm.{site_key}.{runtime_id}"
            source = "vm"
        else:
            flavor_id = f"local.{runtime_id}"
            source = "local"
    else:
        flavor_id = "local.host"
        source = "local"
    return ResourceFlavor(
        flavor_id=flavor_id,
        source=source,
        runtime_id=runtime_id,
        transport=transport,
        site_key=site_key,
        device_id=device_id,
    )
