"""Runner-local resource pressure helpers.

The browser runner needs an admission signal before it claims more work.  This
module reads the container cgroup counters and returns JSON-serialisable state
for both control flow and runner heartbeat telemetry.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

from backend.app.runner.resource_pressure_cpu import (
    build_cpu_delta_snapshot,
    read_cpu_counters,
    reset_cpu_samples_for_tests,
)

_BROWSER_RESOURCE_CLASS = "browser"
_COOLDOWN_UNTIL_EPOCH = 0.0


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_optional_int(name: str) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _default_browser_session_max_active(snapshot: dict[str, Any]) -> int:
    configured_max = snapshot.get("max_inflight") if isinstance(snapshot, dict) else None
    if isinstance(configured_max, int) and configured_max > 0:
        return configured_max
    return 1


def _env_optional_float(name: str) -> Optional[float]:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _read_int(path: Path) -> Optional[int]:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_limit(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    raw = str(raw).strip().lower()
    if not raw or raw == "max":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0 or value >= 2**60:
        return None
    return value


def _ratio(value: Optional[int], limit: Optional[int]) -> Optional[float]:
    if value is None or limit is None or limit <= 0:
        return None
    return max(0.0, min(float(value) / float(limit), 10.0))


def _read_memory_stat(path: Path) -> dict[str, int]:
    raw = _read_text(path)
    stats: dict[str, int] = {}
    if not raw:
        return stats
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            stats[parts[0]] = int(parts[1])
        except (TypeError, ValueError):
            continue
    return stats


def _read_cgroup_counters(cgroup_root: str | Path = "/sys/fs/cgroup") -> dict[str, Any]:
    root = Path(cgroup_root)

    # cgroup v2 layout.
    memory_current = _read_int(root / "memory.current")
    memory_limit_raw = _read_text(root / "memory.max")
    memory_stat = _read_memory_stat(root / "memory.stat")
    pids_current = _read_int(root / "pids.current")
    pids_limit_raw = _read_text(root / "pids.max")

    # cgroup v1 fallback layout.
    if memory_current is None:
        memory_current = _read_int(root / "memory" / "memory.usage_in_bytes")
    if memory_limit_raw is None:
        memory_limit_raw = _read_text(root / "memory" / "memory.limit_in_bytes")
    if not memory_stat:
        memory_stat = _read_memory_stat(root / "memory" / "memory.stat")
    if pids_current is None:
        pids_current = _read_int(root / "pids" / "pids.current")
    if pids_limit_raw is None:
        pids_limit_raw = _read_text(root / "pids" / "pids.max")

    memory_limit = _parse_limit(memory_limit_raw)
    pids_limit = _parse_limit(pids_limit_raw)
    inactive_file = memory_stat.get("inactive_file")
    if inactive_file is None:
        inactive_file = memory_stat.get("total_inactive_file", 0)
    if memory_current is not None:
        working_set = max(0, memory_current - int(inactive_file or 0))
    else:
        working_set = None

    return {
        "memory_current_bytes": memory_current,
        "memory_limit_bytes": memory_limit,
        "memory_limit_raw": memory_limit_raw,
        "memory_inactive_file_bytes": int(inactive_file or 0),
        "memory_working_set_bytes": working_set,
        "pids_current": pids_current,
        "pids_limit": pids_limit,
        "pids_limit_raw": pids_limit_raw,
    }


def is_browser_resource_profile(profile: Any) -> bool:
    """Return True when a runner profile is intended to launch browsers."""
    if profile is None:
        return False
    classes = getattr(profile, "accepted_resource_classes", ()) or ()
    try:
        if _BROWSER_RESOURCE_CLASS in set(str(item).lower() for item in classes):
            return True
    except Exception:
        pass
    code = str(getattr(profile, "profile_code", "") or "").lower()
    return _BROWSER_RESOURCE_CLASS in code


def build_runner_resource_snapshot(
    *,
    profile_code: Optional[str] = None,
    inflight: Optional[int] = None,
    max_inflight: Optional[int] = None,
    available_slots: Optional[int] = None,
    cgroup_root: str | Path = "/sys/fs/cgroup",
    now_epoch: Optional[float] = None,
) -> dict[str, Any]:
    """Build a JSON-safe cgroup resource snapshot for runner heartbeat/admission."""
    now = float(now_epoch if now_epoch is not None else time.time())
    counters = _read_cgroup_counters(cgroup_root)
    cpu_counters = read_cpu_counters(cgroup_root)

    memory_current = counters["memory_current_bytes"]
    memory_limit = counters["memory_limit_bytes"]
    memory_working_set = counters["memory_working_set_bytes"]
    pids_current = counters["pids_current"]
    pids_limit = counters["pids_limit"]

    snapshot: dict[str, Any] = {
        "version": 1,
        "captured_at_epoch": now,
        "profile_code": profile_code,
        "inflight": max(0, int(inflight or 0)),
        "max_inflight": max_inflight,
        "available_slots": available_slots,
        "memory": {
            "current_bytes": memory_current,
            "limit_bytes": memory_limit,
            "limit_raw": counters["memory_limit_raw"],
            "inactive_file_bytes": counters["memory_inactive_file_bytes"],
            "working_set_bytes": memory_working_set,
            "current_ratio": _ratio(memory_current, memory_limit),
            "working_set_ratio": _ratio(memory_working_set, memory_limit),
        },
        "pids": {
            "current": pids_current,
            "limit": pids_limit,
            "limit_raw": counters["pids_limit_raw"],
            "ratio": _ratio(pids_current, pids_limit),
        },
        "cpu": build_cpu_delta_snapshot(
            cgroup_root=cgroup_root,
            now_epoch=now,
            counters=cpu_counters,
        ),
    }
    snapshot["admission"] = evaluate_browser_resource_pressure(
        snapshot,
        now_epoch=now,
    )
    return snapshot


def evaluate_browser_resource_pressure(
    snapshot: dict[str, Any],
    *,
    now_epoch: Optional[float] = None,
) -> dict[str, Any]:
    """Evaluate whether a browser runner should claim more work."""
    global _COOLDOWN_UNTIL_EPOCH

    now = float(now_epoch if now_epoch is not None else time.time())
    cooldown_seconds = max(
        1,
        _env_int("LOCAL_CORE_RUNNER_BROWSER_RESOURCE_COOLDOWN_SECONDS", 300),
    )
    memory_soft_ratio = _env_float("LOCAL_CORE_RUNNER_BROWSER_MEMORY_SOFT_RATIO", 0.78)
    memory_hard_ratio = _env_float("LOCAL_CORE_RUNNER_BROWSER_MEMORY_HARD_RATIO", 0.90)
    pids_soft_ratio = _env_optional_float("LOCAL_CORE_RUNNER_BROWSER_PIDS_SOFT_RATIO")
    pids_hard_ratio = _env_optional_float("LOCAL_CORE_RUNNER_BROWSER_PIDS_HARD_RATIO")
    pids_soft_count = _env_optional_int("LOCAL_CORE_RUNNER_BROWSER_PIDS_SOFT_COUNT")
    pids_hard_count = _env_optional_int("LOCAL_CORE_RUNNER_BROWSER_PIDS_HARD_COUNT")
    cpu_soft_ratio = _env_float("LOCAL_CORE_RUNNER_BROWSER_CPU_SOFT_RATIO", 0.90)
    cpu_hard_ratio = _env_float("LOCAL_CORE_RUNNER_BROWSER_CPU_HARD_RATIO", 0.98)
    cpu_throttled_soft_ratio = _env_optional_float(
        "LOCAL_CORE_RUNNER_BROWSER_CPU_THROTTLED_SOFT_RATIO"
    )
    cpu_throttled_hard_ratio = _env_optional_float(
        "LOCAL_CORE_RUNNER_BROWSER_CPU_THROTTLED_HARD_RATIO"
    )

    memory = snapshot.get("memory") if isinstance(snapshot, dict) else {}
    pids = snapshot.get("pids") if isinstance(snapshot, dict) else {}
    cpu = snapshot.get("cpu") if isinstance(snapshot, dict) else {}
    inflight = snapshot.get("inflight") if isinstance(snapshot, dict) else None
    browser_session_max_active = max(
        1,
        _env_optional_int("LOCAL_CORE_RUNNER_BROWSER_SESSION_MAX_ACTIVE")
        or _default_browser_session_max_active(snapshot),
    )
    memory_ratio = None
    if isinstance(memory, dict):
        memory_ratio = memory.get("working_set_ratio")
        if memory_ratio is None:
            memory_ratio = memory.get("current_ratio")
    pids_ratio = pids.get("ratio") if isinstance(pids, dict) else None
    pids_current = pids.get("current") if isinstance(pids, dict) else None
    cpu_ratio = cpu.get("usage_ratio") if isinstance(cpu, dict) else None
    cpu_throttled_ratio = (
        cpu.get("throttled_ratio") if isinstance(cpu, dict) else None
    )

    reasons: list[str] = []
    hard_reasons: list[str] = []

    if isinstance(memory_ratio, (int, float)):
        if memory_ratio >= memory_hard_ratio:
            hard_reasons.append("memory_hard")
        elif memory_ratio >= memory_soft_ratio:
            reasons.append("memory_soft")

    if isinstance(pids_ratio, (int, float)):
        if pids_hard_ratio is not None and pids_ratio >= pids_hard_ratio:
            hard_reasons.append("pids_hard_ratio")
        elif pids_soft_ratio is not None and pids_ratio >= pids_soft_ratio:
            reasons.append("pids_soft_ratio")

    if isinstance(pids_current, int):
        if pids_hard_count is not None and pids_current >= pids_hard_count:
            hard_reasons.append("pids_hard_count")
        elif pids_soft_count is not None and pids_current >= pids_soft_count:
            reasons.append("pids_soft_count")

    if isinstance(cpu_ratio, (int, float)):
        if cpu_ratio >= cpu_hard_ratio:
            hard_reasons.append("cpu_hard")
        elif cpu_ratio >= cpu_soft_ratio:
            reasons.append("cpu_soft")

    if isinstance(cpu_throttled_ratio, (int, float)):
        if (
            cpu_throttled_hard_ratio is not None
            and cpu_throttled_ratio >= cpu_throttled_hard_ratio
        ):
            hard_reasons.append("cpu_throttled_hard")
        elif (
            cpu_throttled_soft_ratio is not None
            and cpu_throttled_ratio >= cpu_throttled_soft_ratio
        ):
            reasons.append("cpu_throttled_soft")

    if isinstance(inflight, int) and inflight >= browser_session_max_active:
        reasons.append("browser_session_slots")

    if hard_reasons:
        _COOLDOWN_UNTIL_EPOCH = max(_COOLDOWN_UNTIL_EPOCH, now + cooldown_seconds)

    if _COOLDOWN_UNTIL_EPOCH > now:
        state = "cooldown" if not hard_reasons else "hard_cooldown"
        should_defer = True
    elif reasons:
        state = "soft_defer"
        should_defer = True
    else:
        state = "normal"
        should_defer = False

    return {
        "state": state,
        "should_defer": should_defer,
        "reasons": hard_reasons or reasons,
        "memory_soft_ratio": memory_soft_ratio,
        "memory_hard_ratio": memory_hard_ratio,
        "cpu_soft_ratio": cpu_soft_ratio,
        "cpu_hard_ratio": cpu_hard_ratio,
        "browser_session_max_active": browser_session_max_active,
        "cooldown_seconds": cooldown_seconds,
        "cooldown_until_epoch": (
            _COOLDOWN_UNTIL_EPOCH if _COOLDOWN_UNTIL_EPOCH > now else None
        ),
    }


def should_defer_browser_claim(snapshot: Optional[dict[str, Any]]) -> bool:
    if not isinstance(snapshot, dict):
        return False
    admission = snapshot.get("admission")
    if not isinstance(admission, dict):
        return False
    return bool(admission.get("should_defer"))


def resource_failure_retry_delay_seconds() -> int:
    return max(
        15,
        _env_int("LOCAL_CORE_RUNNER_BROWSER_RESOURCE_COOLDOWN_SECONDS", 300),
    )


def classify_subprocess_resource_failure(
    exitcode: Optional[int],
    message: str,
) -> Optional[str]:
    if exitcode == -9:
        return "subprocess_sigkill"
    lowered = (message or "").lower()
    if "browser launch timed out" in lowered:
        return "browser_launch_timeout"
    if "browser resource lease" in lowered or "browser resource guard" in lowered:
        return "browser_resource_lease"
    return None


def _reset_resource_cooldown_for_tests() -> None:
    global _COOLDOWN_UNTIL_EPOCH
    _COOLDOWN_UNTIL_EPOCH = 0.0
    reset_cpu_samples_for_tests()
