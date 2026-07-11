"""Canonical lock-set and request-vector planning for browser tasks."""

from __future__ import annotations

import posixpath
from typing import Any, Mapping

from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.services.runner_resources.lease_keys import build_resource_lease_key
from backend.app.services.runner_resources.requirements import (
    resolve_resource_requirements,
)
from backend.app.services.runner_topology.partitions import normalize_queue_partition


def normalize_profile_identity(raw: Any) -> str | None:
    """Normalize a persisted browser profile path without filesystem access."""

    value = str(raw or "").strip()
    if not value:
        return None
    normalized = posixpath.normpath(value)
    return normalized if normalized not in {"", "."} else None


def workload_envelope_id(workload_code: str, inputs: Mapping[str, Any]) -> str:
    """Return the calibration/admission envelope for one task contract."""

    code = str(workload_code or "").strip()
    if code != "ig_batch_pin_references":
        return code
    source_mode = str(inputs.get("source_mode") or "browser").strip().lower()
    if source_mode not in {"browser", "captured_posts"}:
        source_mode = "browser"
    return f"{code}.{source_mode}"


def summarize_task_candidates(
    payload: dict[str, Any],
    *,
    playbook_metadata: Mapping[str, Any] | None = None,
    processing_task_ids: set[str] | None = None,
    reservation_owner_ids: set[str] | None = None,
    live_owners: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve installed requirements and complete exclusive lock sets."""

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("task candidates must be a list")
    metadata_catalog = playbook_metadata or {}
    processing_ids = processing_task_ids or set()
    owner_ids = reservation_owner_ids or set()
    live_owner_catalog = live_owners or {}
    candidates: list[dict[str, Any]] = []
    missing_lock_identity_count = 0

    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise ValueError("task candidate must be an object")
        task_id = str(raw.get("task_id") or "").strip()
        workload_code = str(raw.get("workload_code") or "").strip()
        context = raw.get("execution_context")
        if not isinstance(context, dict):
            context = {}
        inputs = context.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {}
        requirements = resolve_resource_requirements(
            {"id": task_id, "pack_id": workload_code},
            execution_context=context,
            playbook_metadata=(
                metadata_catalog.get(workload_code)
                if isinstance(metadata_catalog.get(workload_code), Mapping)
                else {}
            ),
        )
        lock_keys = _resolve_lock_keys(
            context,
            workload_code,
            persisted_concurrency_key=str(raw.get("concurrency_key") or ""),
        )
        profile_identity = normalize_profile_identity(
            requirements.ig_profile_lock
        )
        if requirements.ig_profile_lock and profile_identity is None:
            missing_lock_identity_count += 1
        if profile_identity:
            lock_keys.append(
                build_resource_lease_key("ig_profile_lock", profile_identity)
            )
        lock_keys = list(dict.fromkeys(key for key in lock_keys if key))
        status = str(raw.get("status") or "")
        in_processing = task_id in processing_ids
        has_reservation_owner = any(
            task_id and task_id in owner_id for owner_id in owner_ids
        )
        db_heartbeat_fresh = raw.get("heartbeat_fresh") is True
        live_owner = live_owner_catalog.get(task_id)
        if not isinstance(live_owner, Mapping):
            live_owner = {}
        live_owner_fresh = bool(
            status == "running"
            and str(live_owner.get("task_id") or "") == task_id
            and str(live_owner.get("runner_id") or "")
            == str(raw.get("runner_id") or "")
            and int(live_owner.get("ttl_seconds_remaining") or 0) > 0
        )
        candidate = dict(raw)
        candidate.pop("execution_context", None)
        candidate.update(
            {
                "task_id": task_id,
                "workload_code": workload_code,
                "envelope_id": workload_envelope_id(workload_code, inputs),
                "profile_identity": profile_identity,
                "lock_keys": lock_keys,
                "runner_partition": normalize_queue_partition(
                    raw.get("queue_shard"),
                    fallback=None,
                ),
                "db_heartbeat_fresh": db_heartbeat_fresh,
                "heartbeat_fresh": db_heartbeat_fresh or live_owner_fresh,
                "live_owner_fresh": live_owner_fresh,
                "in_processing": in_processing,
                "has_reservation_owner": has_reservation_owner,
                "fresh_live": bool(
                    status == "running"
                    and live_owner_fresh
                    and in_processing
                    and has_reservation_owner
                ),
                "resolved_requirements": requirements.to_dict(),
            }
        )
        candidates.append(candidate)

    candidates.sort(key=_candidate_sort_key)
    running = [item for item in candidates if item.get("status") == "running"]
    return {
        "running_count": len(running),
        "fresh_live_running_count": sum(
            1 for item in running if item.get("fresh_live") is True
        ),
        "stale_running_count": sum(
            1 for item in running if item.get("fresh_live") is not True
        ),
        "missing_lock_identity_count": missing_lock_identity_count,
        "task_candidates": candidates,
    }


def build_candidate_request_plan(
    tasks: dict[str, Any],
    *,
    required_concurrency: int,
    default_request_bytes: int | None,
    envelope_request_bytes: dict[str, int],
    slot_capacity_by_partition: Mapping[str, int],
    available_request_bytes: int,
) -> dict[str, Any]:
    """Select a deterministic non-conflicting task vector for acceptance."""

    if required_concurrency <= 0:
        raise ValueError("required_concurrency must be positive")
    if available_request_bytes < 0:
        raise ValueError("available_request_bytes must not be negative")
    candidates = tasks.get("task_candidates")
    if not isinstance(candidates, list):
        raise ValueError("task candidates must be a list")

    running = [item for item in candidates if item.get("status") == "running"]
    ready = [item for item in candidates if item.get("status") != "running"]
    used_locks: set[str] = set()
    partition_usage: dict[str, int] = {}
    running_lock_conflict_count = 0
    for candidate in running:
        candidate_locks = set(candidate.get("lock_keys") or [])
        if candidate_locks.intersection(used_locks):
            running_lock_conflict_count += 1
        used_locks.update(candidate_locks)
        partition = str(candidate.get("runner_partition") or "")
        partition_usage[partition] = partition_usage.get(partition, 0) + 1

    selected: list[dict[str, Any]] = [
        dict(item) for item in running[:required_concurrency]
    ]
    remaining_request_bytes = int(available_request_bytes)
    lock_blocked_count = 0
    partition_blocked_count = 0
    byte_blocked_count = 0
    for candidate in ready:
        if len(selected) >= required_concurrency:
            break
        candidate_locks = set(candidate.get("lock_keys") or [])
        if candidate_locks.intersection(used_locks):
            lock_blocked_count += 1
            continue
        partition = str(candidate.get("runner_partition") or "")
        capacity = int(slot_capacity_by_partition.get(partition, 0) or 0)
        if partition_usage.get(partition, 0) >= capacity:
            partition_blocked_count += 1
            continue
        envelope_id = str(candidate.get("envelope_id") or "").strip()
        request_bytes = envelope_request_bytes.get(envelope_id)
        if request_bytes is None:
            request_bytes = default_request_bytes
        if request_bytes is not None and int(request_bytes) > remaining_request_bytes:
            byte_blocked_count += 1
            continue
        selected.append(dict(candidate))
        used_locks.update(candidate_locks)
        partition_usage[partition] = partition_usage.get(partition, 0) + 1
        if request_bytes is not None:
            remaining_request_bytes -= int(request_bytes)

    missing_envelopes: list[str] = []
    additional_request_bytes: list[int] = []
    rendered_selected: list[dict[str, Any]] = []
    for candidate in selected:
        envelope_id = str(candidate.get("envelope_id") or "").strip()
        request_bytes = envelope_request_bytes.get(envelope_id)
        if request_bytes is None:
            request_bytes = default_request_bytes
        rendered = dict(candidate)
        if request_bytes is None or int(request_bytes) <= 0:
            missing_envelopes.append(envelope_id or "<missing>")
            rendered["request_bytes"] = None
        else:
            request_bytes = int(request_bytes)
            rendered["request_bytes"] = request_bytes
            if rendered.get("status") != "running":
                additional_request_bytes.append(request_bytes)
        rendered_selected.append(rendered)

    return {
        "selection_mode": (
            "running-first-oldest-compatible-lock-slot-byte-vector"
        ),
        "selected_candidate_count": len(rendered_selected),
        "eligible_candidate_count": len(rendered_selected),
        "selected_candidates": rendered_selected,
        "additional_request_bytes": additional_request_bytes,
        "missing_request_envelopes": sorted(set(missing_envelopes)),
        "running_lock_conflict_count": running_lock_conflict_count,
        "lock_blocked_candidate_count": lock_blocked_count,
        "partition_blocked_candidate_count": partition_blocked_count,
        "byte_blocked_candidate_count": byte_blocked_count,
        "available_request_bytes": int(available_request_bytes),
        "remaining_request_bytes": remaining_request_bytes,
        "selected_partition_usage": partition_usage,
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    status_rank = 0 if candidate.get("status") == "running" else 1
    queued_at = str(candidate.get("frontier_enqueued_at") or "")
    created_at = str(candidate.get("created_at") or "")
    task_id = str(candidate.get("task_id") or "")
    return status_rank, queued_at or created_at, created_at, task_id


__all__ = [
    "build_candidate_request_plan",
    "normalize_profile_identity",
    "summarize_task_candidates",
    "workload_envelope_id",
]
