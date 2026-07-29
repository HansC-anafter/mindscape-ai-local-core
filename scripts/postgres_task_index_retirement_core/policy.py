"""Fail-closed evidence policy for one-at-a-time index retirement."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


REQUIRED_THRESHOLDS = {
    "running_observation_limit": 100,
    "pending_observation_limit": 1000,
    "max_postgres_cpu": 200.0,
    "max_runner_cpu_ratio": 0.90,
    "runner_cpu_sample_count": 5,
    "runner_cpu_sustained_sample_count": 3,
    "runner_cpu_sample_interval_seconds": 2.0,
    "max_endpoint_seconds": 5.0,
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"evidence_file_missing:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence_object_required:{path}")
    return payload


def _timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name}_must_be_iso8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name}_must_include_timezone")
    return parsed.astimezone(timezone.utc)


def runtime_gate_receipt(path: Path, *, now: datetime) -> dict[str, Any]:
    payload = _load_json(path)
    if not payload.get("ok") or payload.get("failures"):
        raise ValueError("runtime_pressure_gate_not_ok")
    thresholds = payload.get("thresholds") or {}
    for key, expected in REQUIRED_THRESHOLDS.items():
        if thresholds.get(key) != expected:
            raise ValueError(f"runtime_pressure_threshold_changed:{key}")
    capacity = payload.get("runner_capacity") or {}
    if int(capacity.get("aggregate_max_inflight") or 0) < 7:
        raise ValueError("runner_capacity_below_7")
    age = now.timestamp() - path.stat().st_mtime
    if age < 0 or age > 65:
        raise ValueError("runtime_pressure_gate_receipt_stale")
    return payload


def index_manifest_entry(
    path: Path,
    *,
    index_name: str,
    expected_definition_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _load_json(path)
    if not payload.get("ok"):
        raise ValueError("task_index_manifest_not_ok")
    matches = [
        dict(entry)
        for entry in payload.get("indexes") or []
        if str(entry.get("index_name")) == index_name
    ]
    if len(matches) != 1:
        raise ValueError("task_index_manifest_exact_entry_required")
    entry = matches[0]
    if entry.get("status") != "retirement_candidate_blocked":
        raise ValueError("index_not_registered_retirement_target")
    if not entry.get("registered"):
        raise ValueError("index_ownership_unregistered")
    if not entry.get("is_valid") or not entry.get("is_ready"):
        raise ValueError("index_invalid_or_not_ready")
    import hashlib

    digest = hashlib.sha256(str(entry.get("definition") or "").encode()).hexdigest()
    if digest != expected_definition_sha256:
        raise ValueError("index_manifest_definition_sha256_mismatch")
    return payload, entry


def evidence_receipt(
    path: Path,
    *,
    evidence_type: str,
    index_name: str,
) -> dict[str, Any]:
    payload = _load_json(path)
    if not payload.get("ok"):
        raise ValueError(f"{evidence_type}_not_ok")
    if payload.get("evidence_type") != evidence_type:
        raise ValueError(f"{evidence_type}_type_mismatch")
    if payload.get("index_name") != index_name:
        raise ValueError(f"{evidence_type}_index_mismatch")
    if not str(payload.get("source_commit") or "").strip():
        raise ValueError(f"{evidence_type}_source_commit_required")
    return payload


def observation_window(
    *,
    observation_started_at: str,
    stats_reset: str | None,
    now: datetime,
) -> dict[str, Any]:
    started = _timestamp(observation_started_at, field_name="observation_started_at")
    if now.astimezone(timezone.utc) - started < timedelta(hours=24):
        raise ValueError("representative_observation_below_24_hours")
    reset = None
    if stats_reset:
        reset = _timestamp(stats_reset, field_name="stats_reset")
        if reset > started:
            raise ValueError("statistics_reset_inside_observation_window")
    return {
        "started_at": started.isoformat(),
        "ended_at": now.astimezone(timezone.utc).isoformat(),
        "stats_reset": reset.isoformat() if reset else None,
    }
