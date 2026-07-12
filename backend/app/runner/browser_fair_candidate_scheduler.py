"""Pure browser-runner candidate selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.services.runner_topology.task_family_registry import (
    resolve_browser_fairness_lane_key,
)


@dataclass(frozen=True)
class BrowserCandidate:
    task_id: str
    pack_id: Optional[str] = None
    playbook_code: Optional[str] = None
    queue_position: int = 0


@dataclass(frozen=True)
class BrowserLaneState:
    lane_key: str
    running_count: int
    first_position: int


@dataclass(frozen=True)
class BrowserFairDecision:
    selected_task_id: Optional[str]
    selected_lane: Optional[str]
    reason: str
    running_count: Optional[int] = None


def _normalize_token(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def normalize_browser_lane_key(
    pack_id: Any,
    playbook_code: Any = None,
) -> Optional[str]:
    """Return the fairness lane used by browser-local playbook scheduling."""

    pack_token = _normalize_token(pack_id)
    playbook_token = _normalize_token(playbook_code)
    return resolve_browser_fairness_lane_key(pack_token, playbook_token)


def _candidate_from_any(candidate: Any, position: int) -> Optional[BrowserCandidate]:
    if isinstance(candidate, BrowserCandidate):
        return candidate
    if isinstance(candidate, dict):
        task_id = _normalize_token(candidate.get("task_id") or candidate.get("id"))
        if not task_id:
            return None
        raw_position = candidate.get("queue_position", position)
        try:
            queue_position = int(raw_position)
        except Exception:
            queue_position = position
        return BrowserCandidate(
            task_id=task_id,
            pack_id=_normalize_token(candidate.get("pack_id")),
            playbook_code=_normalize_token(candidate.get("playbook_code")),
            queue_position=queue_position,
        )

    task_id = _normalize_token(
        getattr(candidate, "task_id", None) or getattr(candidate, "id", None)
    )
    if not task_id:
        return None
    raw_position = getattr(candidate, "queue_position", position)
    try:
        queue_position = int(raw_position)
    except Exception:
        queue_position = position
    return BrowserCandidate(
        task_id=task_id,
        pack_id=_normalize_token(getattr(candidate, "pack_id", None)),
        playbook_code=_normalize_token(getattr(candidate, "playbook_code", None)),
        queue_position=queue_position,
    )


def select_browser_fair_candidate(
    candidates: list[Any],
    running_counts_by_lane: dict[str, int],
    *,
    last_selected_lane: Optional[str] = None,
) -> BrowserFairDecision:
    """Select by running count, then rotate tied lanes after the durable cursor."""

    first_by_lane: dict[str, BrowserCandidate] = {}
    for position, raw_candidate in enumerate(candidates):
        candidate = _candidate_from_any(raw_candidate, position)
        if candidate is None:
            continue
        lane_key = normalize_browser_lane_key(
            candidate.pack_id,
            candidate.playbook_code,
        )
        if not lane_key:
            continue
        current = first_by_lane.get(lane_key)
        if current is None or candidate.queue_position < current.queue_position:
            first_by_lane[lane_key] = candidate

    if not first_by_lane:
        return BrowserFairDecision(
            selected_task_id=None,
            selected_lane=None,
            reason="no_candidates",
        )

    minimum_running_count = min(
        int(running_counts_by_lane.get(lane_key, 0) or 0)
        for lane_key in first_by_lane
    )
    tied_lanes = sorted(
        (
            (lane_key, candidate)
            for lane_key, candidate in first_by_lane.items()
            if int(running_counts_by_lane.get(lane_key, 0) or 0)
            == minimum_running_count
        ),
        key=lambda item: item[1].queue_position,
    )
    selected_index = 0
    tied_lane_keys = [lane_key for lane_key, _candidate in tied_lanes]
    normalized_cursor = _normalize_token(last_selected_lane)
    if normalized_cursor in tied_lane_keys and len(tied_lanes) > 1:
        selected_index = (tied_lane_keys.index(normalized_cursor) + 1) % len(tied_lanes)
    selected_lane, selected_candidate = tied_lanes[selected_index]
    running_count = minimum_running_count
    return BrowserFairDecision(
        selected_task_id=selected_candidate.task_id,
        selected_lane=selected_lane,
        reason=(
            "lane_round_robin"
            if len(tied_lanes) > 1 and normalized_cursor in tied_lane_keys
            else "lane_running_count"
        ),
        running_count=running_count,
    )
