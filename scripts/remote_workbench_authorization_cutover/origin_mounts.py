"""Exact Compose-to-Docker mount normalization for origin proof."""

from __future__ import annotations

from typing import Any, Mapping

from .io import CutoverError


def expected_mounts(service: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in service.get("volumes") or []:
        if not isinstance(item, Mapping) or item.get("type") not in {"bind", "volume"}:
            raise CutoverError("Canonical mount inventory is malformed")
        mount_type = str(item["type"])
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if not source or not target or target in result:
            raise CutoverError("Canonical mount identity is missing or duplicated")
        bind = item.get("bind") if isinstance(item.get("bind"), Mapping) else {}
        result[target] = {
            "type": mount_type,
            "source": source if mount_type == "bind" else None,
            "name": None if mount_type == "bind" else f"mindscape-ai-local-core_{source}",
            "rw": item.get("read_only") is not True,
            "mode": "ro" if item.get("read_only") is True else "rw",
            "propagation": (
                str(bind.get("propagation") or "rprivate")
                if mount_type == "bind"
                else ""
            ),
        }
    return result


def live_mounts(inspect: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("Destination") or ""): {
            "type": str(item.get("Type") or ""),
            "source": str(item.get("Source") or "") if item.get("Type") == "bind" else None,
            "name": str(item.get("Name") or "") if item.get("Type") == "volume" else None,
            "rw": item.get("RW") is True,
            "mode": str(item.get("Mode") or ("rw" if item.get("RW") else "ro")),
            "propagation": str(item.get("Propagation") or ""),
        }
        for item in inspect.get("Mounts") or []
        if isinstance(item, Mapping) and item.get("Type") in {"bind", "volume"}
    }
