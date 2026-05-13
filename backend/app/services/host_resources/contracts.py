"""Shared host resource control-plane contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HostResourceSnapshotContract:
    captured_at: str
    degraded: bool
    host: dict[str, Any]
    capacity: dict[str, Any]
    consumers: list[dict[str, Any]] = field(default_factory=list)
    lanes: list[dict[str, Any]] = field(default_factory=list)
    notifications: list[dict[str, Any]] = field(default_factory=list)
    probe_errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RouteGateDecision:
    permit: bool
    score: int
    reason: str | None = None
    reservation_id: str | None = None
    target_lane: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
