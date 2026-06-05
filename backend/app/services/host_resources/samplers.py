"""Host resource snapshot parsing and synthesis."""

from __future__ import annotations

import shlex
from datetime import datetime, timezone
from typing import Any

from .lane_registry import load_lane_registry


SYSTEM_RESERVED_MEMORY_MB = 8192


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        normalized = _clean_string(item)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _memory_pressure_state(free_percent: int | None) -> str:
    if free_percent is None:
        return "unknown"
    if free_percent < 5:
        return "critical"
    if free_percent < 15:
        return "pressure"
    if free_percent < 30:
        return "busy"
    return "nominal"


def _probe_parsed_value(probe_payload: dict[str, Any], key: str) -> Any:
    probes = probe_payload.get("probes") if isinstance(probe_payload, dict) else {}
    probe = probes.get(key) if isinstance(probes, dict) else {}
    return probe.get("parsed") if isinstance(probe, dict) else None


def _probe_parsed(probe_payload: dict[str, Any], key: str) -> dict[str, Any]:
    parsed = _probe_parsed_value(probe_payload, key)
    return parsed if isinstance(parsed, dict) else {}


def _probe_errors(probe_payload: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    probes = probe_payload.get("probes") if isinstance(probe_payload, dict) else {}
    if not isinstance(probes, dict):
        return errors
    for name, probe in probes.items():
        if not isinstance(probe, dict):
            continue
        if probe.get("ok") is False:
            errors.append(
                {
                    "probe": name,
                    "error": probe.get("error") or probe.get("stderr") or "probe_failed",
                }
            )
    return errors


def _process_port_from_args(args: str) -> int | None:
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()
    for index, token in enumerate(tokens):
        if token == "--port" and index + 1 < len(tokens):
            port = _int_value(tokens[index + 1], default=0)
            return port if port > 0 else None
        if token.startswith("--port="):
            port = _int_value(token.split("=", 1)[1], default=0)
            return port if port > 0 else None
    return None


def _mlx_lane_index(lanes: dict[str, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for lane in lanes.values():
        if not isinstance(lane, dict):
            continue
        model_profile = _dict(lane.get("model_profile"))
        port = _int_value(model_profile.get("port"), default=0)
        if port <= 0:
            continue
        resource_flavor = _clean_string(lane.get("resource_flavor"))
        adapter_id = _clean_string(
            _dict(lane.get("metadata")).get("adapter_id")
            or _dict(lane.get("metadata")).get("runtime_adapter_id")
            or model_profile.get("adapter_id")
        )
        if resource_flavor == "local.mlx.vision" or adapter_id in {"apple_mlx_vlm", "apple_mlx_lm"}:
            indexed[port] = lane
    return indexed


def _mlx_consumer_from_lane(
    *,
    process: dict[str, Any],
    lane: dict[str, Any],
    port: int,
    kind: str,
    rss_mb: float,
) -> dict[str, Any]:
    lane_id = _clean_string(lane.get("lane_id")) or f"port:{port}"
    requirements = _dict(lane.get("requirements"))
    model_profile = _dict(lane.get("model_profile"))
    model = _clean_string(model_profile.get("model") or model_profile.get("model_id"))
    memory_mb = _int_value(requirements.get("memory_mb"), default=0)
    memory_source_detail = _clean_string(requirements.get("memory_source"))
    if memory_mb <= 0:
        memory_mb = _int_value(model_profile.get("memory_reserve_mb"), default=0)
        memory_source_detail = "model_profile.memory_reserve_mb" if memory_mb > 0 else None
    if memory_mb > 0:
        memory_source = "declared"
        confidence = "declared"
    else:
        memory_mb = rss_mb
        memory_source = "rss"
        confidence = "observed"
    groups = _string_list(requirements.get("exclusive_groups"))
    if not groups:
        groups = [
            group
            for group in [
                _clean_string(lane.get("queue_shard")),
                "mlx_runtime",
            ]
            if group
        ]
    return {
        "consumer_id": f"mlx:{lane_id}",
        "label": f"MLX {model}" if model else str(lane.get("label") or "MLX Runtime"),
        "kind": kind,
        "pid": _int_value(process.get("pid")),
        "command": process.get("args") or process.get("command"),
        "memory_mb": memory_mb,
        "memory_source": memory_source,
        "memory_source_detail": memory_source_detail,
        "rss_mb": rss_mb,
        "confidence": confidence,
        "exclusive_groups": groups,
        "lane_id": lane_id,
        "model": model,
        "port": port,
    }


def _unknown_mlx_consumer(
    *,
    process: dict[str, Any],
    port: int | None,
    kind: str,
    rss_mb: float,
) -> dict[str, Any]:
    pid = _int_value(process.get("pid"))
    consumer = {
        "consumer_id": f"mlx:process:{pid}",
        "label": "MLX Runtime",
        "kind": kind,
        "pid": pid,
        "command": process.get("args") or process.get("command"),
        "memory_mb": rss_mb,
        "memory_source": "rss",
        "rss_mb": rss_mb,
        "confidence": "observed",
        "exclusive_groups": ["mlx_runtime"],
    }
    if port:
        consumer["port"] = port
    return consumer


def _consumer_from_process(
    process: dict[str, Any],
    *,
    mlx_lanes_by_port: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    args = str(process.get("args") or "")
    command = str(process.get("command") or "")
    combined = f"{command} {args}".lower()
    pid = _int_value(process.get("pid"))
    rss_mb = round(_int_value(process.get("rss_kb")) / 1024, 1)

    if "mlx_vlm" in combined or "mlx_lm" in combined:
        kind = "mlx_vlm" if "mlx_vlm" in combined else "mlx_lm"
        port = _process_port_from_args(args or command)
        lane = (mlx_lanes_by_port or {}).get(port or 0)
        if lane and port:
            return _mlx_consumer_from_lane(
                process=process,
                lane=lane,
                port=port,
                kind=kind,
                rss_mb=rss_mb,
            )
        return _unknown_mlx_consumer(
            process=process,
            port=port,
            kind=kind,
            rss_mb=rss_mb,
        )
    if "ollama" in combined:
        return {
            "consumer_id": f"ollama:process:{pid}",
            "label": "Ollama",
            "kind": "process",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["ollama"],
        }
    if "comfyui" in combined or "flux" in combined:
        return {
            "consumer_id": f"comfyui_runtime:process:{pid}",
            "label": "ComfyUI Runtime",
            "kind": "process",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["comfyui_generation"],
        }
    if "postgres" in combined:
        return {
            "consumer_id": f"postgresql:process:{pid}",
            "label": "PostgreSQL",
            "kind": "postgresql",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["control_plane_db"],
        }
    if "pgbouncer" in combined:
        return {
            "consumer_id": f"pgbouncer:process:{pid}",
            "label": "PgBouncer",
            "kind": "pgbouncer",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["control_plane_db"],
        }
    if "uvicorn" in combined or "backend.app" in combined:
        return {
            "consumer_id": f"local_core_backend:process:{pid}",
            "label": "Local-Core Backend",
            "kind": "local_core_backend",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["control_plane_api"],
        }
    if "next" in combined or "node" in combined and "web-console" in combined:
        return {
            "consumer_id": f"web_console_frontend:process:{pid}",
            "label": "Web Console Frontend",
            "kind": "web_console_frontend",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["control_plane_frontend"],
        }
    if "playwright" in combined or "chromium" in combined:
        return {
            "consumer_id": f"browser_or_playwright:process:{pid}",
            "label": "Browser / Playwright",
            "kind": "browser_or_playwright",
            "pid": pid,
            "command": args or command,
            "memory_mb": rss_mb,
            "memory_source": "rss",
            "rss_mb": rss_mb,
            "confidence": "observed",
            "exclusive_groups": ["browser_local"],
        }
    return None


def _consumers_from_probe(
    probe_payload: dict[str, Any],
    *,
    lane_registry: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    processes = _probe_parsed_value(probe_payload, "process_census")
    raw_processes = processes if isinstance(processes, list) else []
    mlx_lanes_by_port = _mlx_lane_index(lane_registry or load_lane_registry())
    consumers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for process in raw_processes:
        if not isinstance(process, dict):
            continue
        consumer = _consumer_from_process(process, mlx_lanes_by_port=mlx_lanes_by_port)
        if not consumer:
            continue
        key = str(consumer.get("consumer_id") or "")
        if key in seen:
            continue
        seen.add(key)
        consumers.append(consumer)
    return consumers


def degraded_snapshot(reason: str) -> dict[str, Any]:
    lanes = []
    for lane in load_lane_registry().values():
        lane_copy = dict(lane)
        lane_copy["state"] = "degraded"
        lanes.append(lane_copy)
    return {
        "captured_at": _utc_now_iso(),
        "degraded": True,
        "degraded_reason": reason,
        "host": {
            "os": "unknown",
            "total_memory_bytes": None,
            "memory_pressure": {
                "state": "unknown",
                "free_percent": None,
            },
        },
        "capacity": {
            "memory_mb": 0,
            "reserved_memory_mb": 0,
            "cpu_weight_tokens": 0,
            "llm_lane_tokens": {},
            "vision_lane_tokens": {},
            "db_write_tokens": 0,
        },
        "consumers": [],
        "lanes": lanes,
        "notifications": [
            {
                "notification_id": "host-resource-bridge-degraded",
                "severity": "warning",
                "message": reason,
                "state": "active",
            }
        ],
        "probe_errors": [{"probe": "host_resource_probe", "error": reason}],
    }


def snapshot_from_probe(
    probe_payload: dict[str, Any],
    *,
    paused_lanes: set[str] | None = None,
) -> dict[str, Any]:
    paused_lanes = paused_lanes or set()
    host = probe_payload.get("host") if isinstance(probe_payload, dict) else {}
    total_memory_bytes = _int_value(host.get("total_memory_bytes")) if isinstance(host, dict) else 0
    total_memory_mb = round(total_memory_bytes / 1024 / 1024)
    pressure = _probe_parsed(probe_payload, "memory_pressure")
    free_percent = pressure.get("free_percent")
    if free_percent is not None:
        free_percent = _int_value(free_percent)
    lane_registry = load_lane_registry()
    consumers = _consumers_from_probe(probe_payload, lane_registry=lane_registry)
    reserved_memory_mb = sum(
        _int_value(consumer.get("memory_mb"))
        for consumer in consumers
        if consumer.get("memory_source") == "declared"
    )
    capacity_memory_mb = max(0, total_memory_mb - SYSTEM_RESERVED_MEMORY_MB - reserved_memory_mb)

    lanes: list[dict[str, Any]] = []
    active_groups = {
        group
        for consumer in consumers
        for group in consumer.get("exclusive_groups", [])
        if isinstance(group, str)
    }
    for lane in lane_registry.values():
        lane_copy = dict(lane)
        requirements = dict(lane.get("requirements") or {})
        lane_copy["requirements"] = requirements
        lane_id = str(lane_copy.get("lane_id") or "")
        groups = set(requirements.get("exclusive_groups") or [])
        if lane_id in paused_lanes:
            lane_copy["state"] = "paused"
        elif requirements.get("memory_mb") is None and requirements.get("memory_source") == "unknown":
            lane_copy["state"] = "unknown_requirements"
        elif groups.intersection(active_groups):
            lane_copy["state"] = "busy"
        else:
            lane_copy["state"] = "available"
        lanes.append(lane_copy)

    return {
        "captured_at": probe_payload.get("sampled_at") or _utc_now_iso(),
        "degraded": False,
        "host": {
            "os": "macos" if probe_payload.get("platform") == "darwin" else probe_payload.get("platform"),
            "total_memory_bytes": total_memory_bytes or None,
            "memory_pressure": {
                "state": _memory_pressure_state(free_percent),
                "free_percent": free_percent,
                "swapins": pressure.get("swapins"),
                "swapouts": pressure.get("swapouts"),
            },
        },
        "capacity": {
            "memory_mb": capacity_memory_mb,
            "reserved_memory_mb": reserved_memory_mb,
            "cpu_weight_tokens": 8,
            "llm_lane_tokens": {"heavy": 1},
            "vision_lane_tokens": {"heavy": 1},
            "db_write_tokens": 8,
        },
        "consumers": consumers,
        "lanes": lanes,
        "notifications": [],
        "probe_errors": _probe_errors(probe_payload),
    }
