"""Physical browser-profile identity and request-vector planning."""

from __future__ import annotations

import posixpath
from typing import Any


def normalize_profile_identity(raw: Any) -> str | None:
    """Normalize a persisted browser profile path without filesystem access."""

    value = str(raw or "").strip()
    if not value:
        return None
    normalized = posixpath.normpath(value)
    return normalized if normalized not in {"", "."} else None


def summarize_physical_profiles(payload: dict[str, Any]) -> dict[str, Any]:
    """Collapse task candidates to one representative per physical profile."""

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("task candidates must be a list")

    grouped: dict[str, list[dict[str, Any]]] = {}
    missing_profile_identity_count = 0
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise ValueError("task candidate must be an object")
        profile_identity = normalize_profile_identity(raw.get("profile_path"))
        if profile_identity is None:
            missing_profile_identity_count += 1
            continue
        candidate = dict(raw)
        candidate["profile_identity"] = profile_identity
        grouped.setdefault(profile_identity, []).append(candidate)

    representatives: list[dict[str, Any]] = []
    duplicate_running_profile_count = 0
    running_profile_count = 0
    for profile_identity, items in grouped.items():
        ordered = sorted(items, key=_candidate_sort_key)
        running_items = [item for item in ordered if item.get("status") == "running"]
        if running_items:
            running_profile_count += 1
        if len(running_items) > 1:
            duplicate_running_profile_count += 1
        representative = dict(ordered[0])
        representative["profile_identity"] = profile_identity
        representative["candidate_count"] = len(items)
        representatives.append(representative)

    representatives.sort(key=_candidate_sort_key)
    return {
        "running_count": int(payload.get("running_count") or 0),
        "running_physical_profile_count": running_profile_count,
        "runnable_physical_profile_count": len(representatives),
        "duplicate_running_physical_profile_count": (
            duplicate_running_profile_count
        ),
        "missing_profile_identity_count": missing_profile_identity_count,
        "physical_profile_candidates": representatives,
    }


def build_candidate_request_plan(
    tasks: dict[str, Any],
    *,
    required_concurrency: int,
    default_request_bytes: int | None,
    workload_request_bytes: dict[str, int],
) -> dict[str, Any]:
    """Build the deterministic heterogeneous request vector for acceptance."""

    if required_concurrency <= 0:
        raise ValueError("required_concurrency must be positive")
    candidates = tasks.get("physical_profile_candidates")
    if not isinstance(candidates, list):
        raise ValueError("physical profile candidates must be a list")

    selected: list[dict[str, Any]] = []
    missing_workloads: list[str] = []
    additional_request_bytes: list[int] = []
    for raw_candidate in candidates[:required_concurrency]:
        if not isinstance(raw_candidate, dict):
            raise ValueError("physical profile candidate must be an object")
        workload_code = str(raw_candidate.get("workload_code") or "").strip()
        request_bytes = workload_request_bytes.get(workload_code)
        if request_bytes is None:
            request_bytes = default_request_bytes
        candidate = dict(raw_candidate)
        if request_bytes is None or int(request_bytes) <= 0:
            missing_workloads.append(workload_code or "<missing>")
            candidate["request_bytes"] = None
        else:
            request_bytes = int(request_bytes)
            candidate["request_bytes"] = request_bytes
            if candidate.get("status") != "running":
                additional_request_bytes.append(request_bytes)
        selected.append(candidate)

    return {
        "selection_mode": "running-first-oldest-per-physical-profile",
        "selected_candidate_count": len(selected),
        "selected_candidates": selected,
        "additional_request_bytes": additional_request_bytes,
        "missing_request_workloads": sorted(set(missing_workloads)),
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    status_rank = 0 if candidate.get("status") == "running" else 1
    queued_at = str(candidate.get("frontier_enqueued_at") or "")
    created_at = str(candidate.get("created_at") or "")
    task_id = str(candidate.get("task_id") or "")
    return status_rank, queued_at or created_at, created_at, task_id
