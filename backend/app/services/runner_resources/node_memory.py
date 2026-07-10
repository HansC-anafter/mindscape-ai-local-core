"""Docker-VM memory snapshot helpers for runner node admission."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _parse_meminfo(raw: str | None) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in (raw or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parts = value.strip().split()
        if not parts:
            continue
        try:
            parsed = int(parts[0])
        except (TypeError, ValueError):
            continue
        multiplier = 1024 if len(parts) > 1 and parts[1].lower() == "kb" else 1
        values[key.strip()] = max(0, parsed * multiplier)
    return values


def _parse_limit(raw: str | None) -> int | None:
    normalized = str(raw or "").strip().lower()
    if not normalized or normalized == "max":
        return None
    try:
        value = int(normalized)
    except (TypeError, ValueError):
        return None
    return value if 0 < value < 2**60 else None


def _parse_pressure(raw: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in (raw or "").splitlines():
        parts = line.split()
        if not parts:
            continue
        lane = parts[0]
        values: dict[str, float | int] = {}
        for item in parts[1:]:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            try:
                values[key] = int(value) if key == "total" else float(value)
            except (TypeError, ValueError):
                continue
        result[lane] = values
    return result


def read_node_memory_snapshot(
    *,
    meminfo_path: str | Path = "/proc/meminfo",
    pressure_path: str | Path = "/proc/pressure/memory",
    cgroup_root: str | Path = "/sys/fs/cgroup",
) -> dict[str, Any]:
    values = _parse_meminfo(_read_text(Path(meminfo_path)))
    total_bytes = values.get("MemTotal")
    available_bytes = values.get("MemAvailable")
    root = Path(cgroup_root)
    cgroup_limit = _parse_limit(_read_text(root / "memory.max"))
    if cgroup_limit is None:
        cgroup_limit = _parse_limit(
            _read_text(root / "memory" / "memory.limit_in_bytes")
        )
    return {
        "available": bool(total_bytes and available_bytes is not None),
        "total_bytes": total_bytes,
        "available_bytes": available_bytes,
        "cgroup_limit_bytes": cgroup_limit,
        "pressure": _parse_pressure(_read_text(Path(pressure_path))),
        "source": "proc_meminfo",
    }
