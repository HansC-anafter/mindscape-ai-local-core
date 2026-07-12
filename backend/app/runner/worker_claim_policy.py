"""Runner worker claim selection and parked-task policy helpers."""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.app.services.runner_topology import (
    normalize_queue_partition,
    runner_profile_can_claim_task,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.host_resources.route_identity_projection import (
    read_route_identity_projections,
)
from backend.app.runner.browser_fair_candidate_scheduler import (
    select_browser_fair_candidate,
)
from backend.app.runner.browser_fairness_cursor import (
    read_browser_fairness_cursor,
    write_browser_fairness_cursor,
)
from backend.app.runner.resource_pressure import is_browser_resource_profile
from backend.app.runner.worker_transport import _normalize_task_id, _resolve_task_queue_shard

logger = logging.getLogger("backend.app.runner.worker")


def _worker_facade():
    return sys.modules.get("backend.app.runner.worker")


def _facade_attr(name: str, fallback):
    facade = _worker_facade()
    return getattr(facade, name, fallback) if facade is not None else fallback

def _host_route_gate_enabled() -> bool:
    raw = os.getenv("LOCAL_CORE_HOST_RESOURCE_ROUTE_GATE_ENABLED", "true")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _runner_claim_gate_status() -> dict:
    try:
        from backend.app.services.host_resources import get_runner_claim_gate

        return get_runner_claim_gate()
    except Exception:
        return {"state": "open", "source": "unavailable", "persisted": False}


def _runner_claim_gate_paused() -> tuple[bool, dict]:
    gate = _facade_attr("_runner_claim_gate_status", _runner_claim_gate_status)()
    return gate.get("state") == "paused", gate


def _route_drain_after_current_status() -> dict:
    if not _host_route_gate_enabled():
        return {"active": False, "source": "disabled", "reservation_ids": []}
    try:
        from backend.app.services.host_resources import route_gate

        active_reservations = route_gate.get_active_route_reservations()
        drain_reservations = route_gate.drain_after_current_reservations(
            active_reservations
        )
        return {
            "active": bool(drain_reservations),
            "source": "route_reservation",
            "reservation_ids": [
                str(reservation.get("reservation_id") or "")
                for reservation in drain_reservations
                if isinstance(reservation, dict)
            ],
        }
    except Exception:
        return {"active": False, "source": "unavailable", "reservation_ids": []}


async def _dequeue_by_route_gate_policy(
    queue_cycle: list[RedisRunnerQueueStore],
    *,
    runner_profile,
    visibility_timeout_sec: int,
    scan_limit: int,
    active_pack_ids: set[str] | None = None,
) -> tuple[Optional[str], Optional[RedisRunnerQueueStore], bool]:
    if not queue_cycle or scan_limit <= 0:
        return None, None, False
    if not _host_route_gate_enabled():
        return None, None, False

    try:
        from backend.app.services.host_resources import route_gate

        active_reservations = route_gate.get_active_route_reservations()
    except Exception:
        return None, None, False

    candidates: list[dict] = []
    seen: set[str] = set()
    for queue_store in queue_cycle:
        client = await queue_store._get_client()
        if not client:
            continue
        try:
            candidate_ids = await client.lrange(
                queue_store.q_pending,
                0,
                max(0, scan_limit - 1),
            )
        except Exception as e:
            logger.warning(
                "[Worker] Failed to scan ready queue %s for route gate: %s",
                queue_store.pack_id,
                e,
            )
            continue
        task_ids: list[str] = []
        positions: dict[str, int] = {}
        for position, raw_task_id in enumerate(candidate_ids):
            task_id = _normalize_task_id(raw_task_id).strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            task_ids.append(task_id)
            positions[task_id] = position

        projections = await read_route_identity_projections(client, task_ids)
        for task_id in task_ids:
            projection = projections.get(task_id)
            if not projection:
                logger.debug(
                    "[Worker] Route identity projection missing task=%s queue=%s",
                    task_id,
                    queue_store.pack_id,
                )
                continue
            if not _facade_attr("runner_profile_can_claim_task", runner_profile_can_claim_task)(runner_profile, projection):
                continue
            candidates.append(
                {
                    **projection,
                    "queue": queue_store.pack_id,
                    "queue_position": positions.get(task_id, 0),
                    "queue_store": queue_store,
                    "pack_id": projection.get("pack_id"),
                    "route_identity": projection.get("route_identity") or {},
                }
            )

    selection = route_gate.select_candidate_policy(
        candidates,
        active_reservations=active_reservations,
        reserved_share_pack_ids=[],
        active_pack_ids=active_pack_ids or set(),
    )
    if selection.get("drain_wait"):
        return None, None, True
    selected = selection.get("selected")
    if not isinstance(selected, dict):
        return None, None, False
    task_id = str(selected.get("task_id") or "").strip()
    queue_store = selected.get("queue_store")
    if not task_id or not hasattr(queue_store, "promote_pending_task_by_id"):
        return None, None, False
    moved = await queue_store.promote_pending_task_by_id(
        task_id,
        visibility_timeout_sec=visibility_timeout_sec,
    )
    if moved:
        logger.info(
            "[Worker] Route gate policy selected task %s reason=%s queue=%s",
            task_id,
            selection.get("reason"),
            queue_store.pack_id,
        )
        return moved, queue_store, False
    return None, None, False


async def _dequeue_by_browser_fair_candidate_policy(
    queue_cycle: list[RedisRunnerQueueStore],
    *,
    tasks_store: TasksStore,
    runner_profile,
    visibility_timeout_sec: int,
    scan_limit: int,
) -> tuple[Optional[str], Optional[RedisRunnerQueueStore], bool]:
    if (
        not queue_cycle
        or scan_limit <= 0
        or not is_browser_resource_profile(runner_profile)
    ):
        return None, None, False

    try:
        from backend.app.services.host_resources import route_gate

        active_reservations = route_gate.get_active_route_reservations()
    except Exception:
        active_reservations = []

    candidates: list[dict] = []
    cursor_client = None
    seen: set[str] = set()
    for queue_store in queue_cycle:
        client = await queue_store._get_client()
        if not client:
            continue
        if cursor_client is None:
            cursor_client = client
        try:
            candidate_ids = await client.lrange(
                queue_store.q_pending,
                0,
                max(0, scan_limit - 1),
            )
        except Exception as e:
            logger.warning(
                "[Worker] Failed to scan ready queue %s for browser fairness: %s",
                queue_store.pack_id,
                e,
            )
            continue

        task_ids: list[str] = []
        positions: dict[str, int] = {}
        for position, raw_task_id in enumerate(candidate_ids):
            task_id = _normalize_task_id(raw_task_id).strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            task_ids.append(task_id)
            positions[task_id] = position
        if not task_ids:
            continue

        route_projections = await read_route_identity_projections(client, task_ids)
        db_projections = await asyncio.to_thread(
            tasks_store.list_runner_candidate_projections_by_ids,
            task_ids,
            queue_store.pack_id,
        )
        projections_by_id = {
            str(
                projection.get("task_id") or projection.get("id") or ""
            ).strip(): projection
            for projection in db_projections
            if str(projection.get("task_id") or projection.get("id") or "").strip()
        }
        for task_id in task_ids:
            projection = projections_by_id.get(task_id)
            if not projection:
                continue
            route_projection = route_projections.get(task_id) or {}
            route_identity = (
                route_projection.get("route_identity")
                if isinstance(route_projection, dict)
                else None
            )
            candidate = {
                **projection,
                "queue": queue_store.pack_id,
                "queue_position": positions.get(task_id, 0),
                "queue_store": queue_store,
                "route_identity": (
                    route_identity if isinstance(route_identity, dict) else {}
                ),
            }
            if not _facade_attr("runner_profile_can_claim_task", runner_profile_can_claim_task)(runner_profile, candidate):
                continue
            candidates.append(candidate)

    if not candidates:
        return None, None, False

    route_selection = route_gate.select_candidate_policy(
        candidates,
        active_reservations=active_reservations,
        reserved_share_pack_ids=[],
        active_pack_ids=set(),
    )
    if route_selection.get("drain_wait"):
        return None, None, True

    selected = route_selection.get("selected")
    reason = str(route_selection.get("reason") or "")
    if reason == "route_reservation" and isinstance(selected, dict):
        task_id = str(selected.get("task_id") or selected.get("id") or "").strip()
        queue_store = selected.get("queue_store")
        if task_id and hasattr(queue_store, "promote_pending_task_by_id"):
            moved = await queue_store.promote_pending_task_by_id(
                task_id,
                visibility_timeout_sec=visibility_timeout_sec,
            )
            if moved:
                logger.info(
                    "[Worker] Browser route policy selected task %s queue=%s",
                    task_id,
                    queue_store.pack_id,
                )
                return moved, queue_store, False
        return None, None, False

    queue_shard = queue_cycle[0].pack_id
    running_counts = await asyncio.to_thread(
        tasks_store.count_running_browser_lanes,
        queue_shard,
    )
    last_selected_lane = None
    if cursor_client is not None:
        try:
            last_selected_lane = await read_browser_fairness_cursor(
                cursor_client,
                queue_shard=queue_shard,
            )
        except Exception as exc:
            logger.warning(
                "[Worker] Failed to read browser fairness cursor queue=%s: %s",
                queue_shard,
                exc,
            )
    fair_decision = select_browser_fair_candidate(
        candidates,
        running_counts,
        last_selected_lane=last_selected_lane,
    )
    if not fair_decision.selected_task_id:
        return None, None, False

    selected_candidate = next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("task_id") or candidate.get("id") or "").strip()
            == fair_decision.selected_task_id
        ),
        None,
    )
    if not selected_candidate:
        return None, None, False
    queue_store = selected_candidate.get("queue_store")
    if not hasattr(queue_store, "promote_pending_task_by_id"):
        return None, None, False

    moved = await queue_store.promote_pending_task_by_id(
        fair_decision.selected_task_id,
        visibility_timeout_sec=visibility_timeout_sec,
    )
    if moved:
        if cursor_client is not None and fair_decision.selected_lane:
            try:
                await write_browser_fairness_cursor(
                    cursor_client,
                    queue_shard=queue_shard,
                    lane_key=fair_decision.selected_lane,
                )
            except Exception as exc:
                logger.warning(
                    "[Worker] Failed to write browser fairness cursor queue=%s lane=%s: %s",
                    queue_shard,
                    fair_decision.selected_lane,
                    exc,
                )
        logger.info(
            "[Worker] Browser fair policy selected task %s lane=%s running_count=%s queue=%s",
            fair_decision.selected_task_id,
            fair_decision.selected_lane,
            fair_decision.running_count,
            queue_store.pack_id,
        )
        return moved, queue_store, False
    return None, None, False


def _build_parked_task_update(
    task_ctx: Optional[dict],
    *,
    reason: str,
    delay_seconds: int,
    now: Optional[datetime] = None,
    dependency_hold: Optional[dict] = None,
    lock_key: Optional[str] = None,
    conflicting_lock_key: Optional[str] = None,
    current_queue_shard: Optional[str] = None,
) -> dict:
    base_now = now or datetime.now(timezone.utc)
    next_eligible_at = base_now + timedelta(seconds=delay_seconds)

    ctx2 = dict(task_ctx) if isinstance(task_ctx, dict) else {}
    previous_runner_id = ctx2.pop("runner_id", None)
    ctx2.pop("heartbeat_at", None)
    if previous_runner_id and not ctx2.get("last_runner_id"):
        ctx2["last_runner_id"] = previous_runner_id
    ctx2["resume_after"] = next_eligible_at.isoformat()
    ctx2.pop("resource_admission", None)
    ctx2.pop("runner_resource_leases", None)

    blocked_payload: dict = {}

    if reason == "dependency_hold":
        ctx2.pop("runner_skip_reason", None)
        ctx2.pop("runner_skip_lock_key", None)
        ctx2.pop("runner_skip_conflict_lock_key", None)
        if dependency_hold:
            ctx2["dependency_hold"] = dependency_hold
            blocked_payload["dependency_hold"] = dependency_hold
        else:
            ctx2.pop("dependency_hold", None)
    elif reason == "concurrency_locked":
        ctx2.pop("dependency_hold", None)
        ctx2["runner_skip_reason"] = "concurrency_locked"
        if lock_key:
            ctx2["runner_skip_lock_key"] = lock_key
            blocked_payload["lock_key"] = lock_key
        else:
            ctx2.pop("runner_skip_lock_key", None)
        if conflicting_lock_key:
            ctx2["runner_skip_conflict_lock_key"] = conflicting_lock_key
            blocked_payload["conflicting_lock_key"] = conflicting_lock_key
        else:
            ctx2.pop("runner_skip_conflict_lock_key", None)

    return {
        "execution_context": ctx2,
        "next_eligible_at": next_eligible_at,
        "blocked_reason": reason,
        "blocked_payload": blocked_payload or None,
        "frontier_state": "cold",
        "frontier_enqueued_at": None,
        "queue_shard": (
            normalize_queue_partition(current_queue_shard, fallback=None)
            or _resolve_task_queue_shard(ctx2.get("playbook_code") or "", ctx2)
        ),
    }
