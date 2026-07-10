"""Read cgroup memory-event counters without inferring task ownership."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

_OOM_COUNTERS = ("oom", "oom_kill", "oom_group_kill")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _parse_flat_counters(raw: str | None) -> dict[str, int]:
    counters: dict[str, int] = {}
    for line in (raw or "").splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            counters[parts[0]] = max(0, int(parts[1]))
        except (TypeError, ValueError):
            continue
    return counters


def read_cgroup_memory_events(
    cgroup_root: str | Path = "/sys/fs/cgroup",
) -> dict[str, Any]:
    """Return v2 OOM counters; v1 failcnt is telemetry only."""
    root = Path(cgroup_root)
    raw_v2 = _read_text(root / "memory.events")
    if raw_v2 is not None:
        counters = _parse_flat_counters(raw_v2)
        return {
            "available": True,
            "cgroup_version": 2,
            "counters": {
                key: int(counters.get(key, 0))
                for key in ("low", "high", "max", *_OOM_COUNTERS)
            },
            "v1_failcnt": None,
        }

    raw_failcnt = _read_text(root / "memory" / "memory.failcnt")
    try:
        failcnt = max(0, int(raw_failcnt)) if raw_failcnt is not None else None
    except (TypeError, ValueError):
        failcnt = None
    return {
        "available": False,
        "cgroup_version": 1 if raw_failcnt is not None else None,
        "counters": {},
        "v1_failcnt": failcnt,
    }


def memory_event_delta(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return monotonic v2 deltas; counter reset/unavailability is explicit."""
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return {"available": False, "reason": "snapshot_unavailable", "counters": {}}
    if not before.get("available") or not after.get("available"):
        return {"available": False, "reason": "events_unavailable", "counters": {}}
    if before.get("cgroup_version") != 2 or after.get("cgroup_version") != 2:
        return {"available": False, "reason": "cgroup_v2_required", "counters": {}}

    before_counters = before.get("counters")
    after_counters = after.get("counters")
    if not isinstance(before_counters, Mapping) or not isinstance(after_counters, Mapping):
        return {"available": False, "reason": "counter_map_unavailable", "counters": {}}

    deltas: dict[str, int] = {}
    for key in _OOM_COUNTERS:
        try:
            previous = int(before_counters.get(key, 0) or 0)
            current = int(after_counters.get(key, 0) or 0)
        except (TypeError, ValueError):
            return {"available": False, "reason": "counter_invalid", "counters": {}}
        if current < previous:
            return {"available": False, "reason": "counter_reset", "counters": {}}
        deltas[key] = current - previous
    return {"available": True, "reason": None, "counters": deltas}


def has_oom_kill_delta(delta: Mapping[str, Any] | None) -> bool:
    if not isinstance(delta, Mapping) or not delta.get("available"):
        return False
    counters = delta.get("counters")
    if not isinstance(counters, Mapping):
        return False
    return int(counters.get("oom_kill", 0) or 0) > 0 or int(
        counters.get("oom_group_kill", 0) or 0
    ) > 0
