"""Small control helpers for the runner worker loop."""

import asyncio
import logging
import os
import socket
import sys
from datetime import datetime, timezone

from backend.app.services.runner_resources import (
    build_runner_resource_heartbeat,
    publish_runner_resource_heartbeat,
)
from backend.app.services.host_resources.runner_claim_modes import (
    RunnerClaimControl,
    active_runner_claim_control,
    get_runner_claim_control,
    runner_claims_enabled,
)
from backend.app.runner.db_pool_pressure import (
    DbPoolPressureDecision,
    check_db_pool_pressure,
    should_write_postgres_heartbeat,
)
from backend.app.runner.resource_pressure import build_runner_resource_snapshot
from backend.app.runner.restart import _check_restart_sentinel
from backend.app.runner.restart import _RESTART_DRAIN_TIMEOUT_SECONDS
from backend.app.runner.worker_db_budget import (
    WorkerDbBudgetDecision,
    decide_worker_db_budget,
)

logger = logging.getLogger("backend.app.runner.worker")


def _maintenance_only_claim_control(runner_id: str) -> RunnerClaimControl | None:
    raw = os.getenv("LOCAL_CORE_RUNNER_MAINTENANCE_ONLY")
    if raw is None or raw.strip().lower() in {"", "0", "false", "no", "off"}:
        return None
    return RunnerClaimControl(
        runner_id=str(runner_id or "").strip(),
        mode="drain",
        reason="maintenance_only",
        updated_by="environment",
        source="environment",
    )

def _build_initial_resource_snapshot(runner_profile, *, inflight: int, max_inflight: int):
    try:
        return build_runner_resource_snapshot(
            profile_code=runner_profile.profile_code,
            inflight=inflight,
            max_inflight=max_inflight,
        )
    except Exception:
        return None


async def _resolve_loop_claim_budget(
    redis_queue,
    *,
    runner_id: str,
    runner_profile,
    inflight: int,
    max_inflight: int,
):
    runner_claim_control = _maintenance_only_claim_control(runner_id)
    if runner_claim_control is None:
        try:
            runner_claim_control = await get_runner_claim_control(
                redis_queue,
                runner_id=runner_id,
            )
        except Exception:
            runner_claim_control = active_runner_claim_control(runner_id)
    runner_claiming_enabled = runner_claims_enabled(runner_claim_control)

    if runner_claiming_enabled:
        try:
            db_pressure = await check_db_pool_pressure(
                redis_queue,
                owner_id=f"{runner_id}:claim",
            )
        except Exception as exc:
            logger.warning("PgBouncer pressure check failed in runner loop: %s", exc)
            db_pressure = DbPoolPressureDecision.paused_for(
                "pgbouncer_pressure_probe_failed"
            )
        db_budget = decide_worker_db_budget(
            db_pressure,
            profile_code=runner_profile.profile_code,
            inflight=inflight,
            max_inflight=max_inflight,
        )
        return runner_claim_control, runner_claiming_enabled, db_pressure, db_budget

    reason = f"runner_claim_mode_{runner_claim_control.mode}"
    db_pressure = DbPoolPressureDecision.open(reason=reason)
    db_budget = WorkerDbBudgetDecision(
        allow_claim_scan=False,
        claim_scan_limit_multiplier=0.0,
        allow_release_maintenance=True,
        allow_postgres_heartbeat=False,
        wait_seconds=0,
        reason=reason,
    )
    return runner_claim_control, runner_claiming_enabled, db_pressure, db_budget


def _maybe_write_postgres_runner_heartbeat(
    *,
    enabled: bool,
    tasks_store,
    runner_id: str,
    runner_profile,
    inflight: int,
    resource_snapshot,
    db_budget,
    db_pressure,
    db_recovery_backoff,
    runner_claiming_enabled: bool,
    last_write_epoch: float,
    next_pressure_log_at: float,
) -> tuple[float, float]:
    if not enabled:
        return last_write_epoch, next_pressure_log_at

    now_epoch = datetime.now(timezone.utc).timestamp()
    if db_budget.allow_postgres_heartbeat and should_write_postgres_heartbeat(
        db_pressure,
        now_epoch=now_epoch,
        last_write_epoch=last_write_epoch,
    ):
        try:
            tasks_store.upsert_runner_heartbeat(
                runner_id,
                profile_code=runner_profile.profile_code,
                hostname=socket.gethostname(),
                inflight=inflight,
                resource_snapshot=resource_snapshot,
            )
            return now_epoch, next_pressure_log_at
        except Exception as exc:
            db_recovery_backoff.note_failure(exc)
            return last_write_epoch, next_pressure_log_at

    if runner_claiming_enabled:
        now_loop = asyncio.get_event_loop().time()
        if now_loop >= next_pressure_log_at:
            logger.warning(
                "Postgres runner heartbeat skipped while PgBouncer pressure "
                "is active profile=%s reason=%s inflight=%s",
                runner_profile.profile_code,
                db_pressure.reason,
                inflight,
            )
            next_pressure_log_at = now_loop + 30.0
    return last_write_epoch, next_pressure_log_at


async def _publish_resource_heartbeat(
    redis_queue,
    *,
    runner_id: str,
    runner_profile,
    capacity,
    resource_snapshot,
    runner_claim_control,
) -> None:
    try:
        await publish_runner_resource_heartbeat(
            redis_queue,
            build_runner_resource_heartbeat(
                runner_id=runner_id,
                profile_code=runner_profile.profile_code,
                queue_shards=list(runner_profile.accepted_queue_partitions),
                capacity=capacity,
                resource_snapshot=resource_snapshot,
                claim_control=runner_claim_control.to_dict(),
            ),
        )
    except Exception:
        pass


async def _exit_for_restart_if_requested(inflight: set[asyncio.Task]) -> None:
    if not _check_restart_sentinel():
        return
    if inflight:
        logger.info(
            "Restart sentinel: waiting for %d inflight tasks to drain (max %ds)",
            len(inflight),
            _RESTART_DRAIN_TIMEOUT_SECONDS,
        )
        drain_deadline = asyncio.get_event_loop().time() + _RESTART_DRAIN_TIMEOUT_SECONDS
        while inflight and asyncio.get_event_loop().time() < drain_deadline:
            _discard_finished_tasks(inflight)
            if inflight:
                await asyncio.sleep(1.0)
        if inflight:
            logger.warning(
                "Restart sentinel: %d tasks still inflight after drain timeout, forcing exit",
                len(inflight),
            )
    logger.info("Runner exiting for restart (sentinel)")
    sys.exit(1)


def _discard_finished_tasks(inflight: set[asyncio.Task]) -> None:
    try:
        done = {task for task in inflight if task.done()}
        for task in done:
            inflight.discard(task)
            try:
                _ = task.result()
            except Exception:
                pass
    except Exception:
        pass
