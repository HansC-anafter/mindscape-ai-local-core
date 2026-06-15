"""Runner worker one-task claim, admission, lock, and dispatch path."""

import asyncio
import logging
from datetime import datetime, timezone

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_resources import (
    RedisResourceLeaseStore,
    acquire_task_resource_admission,
    build_resource_wait_task_update,
    release_acquired_resource_leases,
    resolve_resource_requirements,
)
from backend.app.services.runner_topology import (
    resolve_installed_playbook_runner_metadata,
    resolve_target_runner_profile,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.runner.claim_admission import decide_runner_claim_admission
from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.database_backoff import RunnerDatabaseRecoveryBackoff
from backend.app.runner.dependency_check import DependencyChecker
from backend.app.runner.task_executor import _run_single_task
from backend.app.runner.utils import _utc_now
from backend.app.runner.worker_claim_policy import _build_parked_task_update
from backend.app.runner.worker_db_budget import WorkerDbBudgetDecision
from backend.app.runner.worker_transport import (
    _pending_task_runnable_from_queue,
    _repair_misqueued_task_if_needed,
)

logger = logging.getLogger("backend.app.runner.worker")


async def _dispatch_claimed_task(
    task_id: str,
    task_queue: RedisRunnerQueueStore,
    *,
    tasks_store: TasksStore,
    runner_id: str,
    redis_queue: RedisRunnerQueueStore,
    runner_profile,
    db_budget: WorkerDbBudgetDecision,
    resource_snapshot,
    capacity,
    dep_checker: DependencyChecker,
    visibility_timeout_sec: int,
    lock_ttl_seconds: int,
    db_recovery_backoff: RunnerDatabaseRecoveryBackoff,
) -> asyncio.Task | None:
    lock_owner_id = f"{runner_id}:{task_id}"
    resource_lease_store = None
    resource_decision = None

    try:
        # Rehydrate task metadata from DB (as source of truth)
        # If the task doesn't exist or is deeply corrupt, deadletter it.
        t_data = await asyncio.to_thread(tasks_store.get_task, task_id)
        if not t_data:
            logger.error(
                f"[Worker] Task {task_id} not found in DB but was in queue. Dropping from processing."
            )
            await task_queue.ack_task(task_id)
            return None

        if t_data.status != TaskStatus.PENDING:
            logger.info(
                f"[Worker] Task {task_id} popped but no longer PENDING (status: {t_data.status.value}). Dropping duplicate queue item."
            )
            if t_data.status == TaskStatus.RUNNING:
                await task_queue.touch_visibility_timeout(
                    task_id,
                    added_time_sec=visibility_timeout_sec,
                )
            else:
                await task_queue.ack_task(task_id)
            return None

        if not _pending_task_runnable_from_queue(t_data):
            logger.info(
                "[Worker] Task %s popped but not runnable "
                "(frontier_state=%s blocked_reason=%s). Dropping stale queue item.",
                task_id,
                getattr(t_data, "frontier_state", None),
                getattr(t_data, "blocked_reason", None),
            )
            await task_queue.ack_task(task_id)
            return None

        if await _repair_misqueued_task_if_needed(task_id, t_data, task_queue):
            return None

        claim_admission = decide_runner_claim_admission(
            t_data,
            runner_profile,
            db_budget,
            resource_snapshot,
        )
        if not claim_admission.allow:
            admission_payload = claim_admission.observability
            logger.info(
                "[Worker] Claim admission deferred task=%s reason=%s profile=%s target_profile=%s queue=%s delay_seconds=%s db_budget_reason=%s workspace_id=%s pack_id=%s task_type=%s",
                task_id,
                claim_admission.reason,
                runner_profile.profile_code,
                admission_payload.get("target_runner_profile")
                or resolve_target_runner_profile(t_data),
                getattr(t_data, "queue_shard", None),
                claim_admission.delay_seconds,
                admission_payload.get("db_budget_reason"),
                admission_payload.get("workspace_id"),
                admission_payload.get("pack_id"),
                admission_payload.get("task_type"),
            )
            await task_queue.nack_task_to_delayed(
                task_id,
                delay_sec=max(1, claim_admission.delay_seconds or 5),
            )
            return None

        try:
            from backend.app.services.host_resources.workspace_quota_admission import (
                decide_workspace_quota_admission_for_task,
            )

            workspace_quota_decision = await asyncio.to_thread(
                decide_workspace_quota_admission_for_task,
                t_data,
            )
        except Exception as exc:
            logger.warning(
                "Workspace quota admission unavailable for task %s: %s",
                task_id,
                exc,
            )
            workspace_quota_decision = None
        claim_admission = decide_runner_claim_admission(
            t_data,
            runner_profile,
            db_budget,
            resource_snapshot,
            workspace_quota_decision=workspace_quota_decision,
        )
        if not claim_admission.allow and claim_admission.action == "park":
            now_dt = datetime.now(timezone.utc)
            quota_payload = claim_admission.workspace_quota_payload or {}
            parked_update = _build_parked_task_update(
                (
                    t_data.execution_context
                    if isinstance(t_data.execution_context, dict)
                    else {}
                ),
                reason=claim_admission.reason,
                delay_seconds=max(1, claim_admission.delay_seconds or 10),
                now=now_dt,
                current_queue_shard=getattr(t_data, "queue_shard", None),
            )
            parked_context = dict(parked_update.get("execution_context") or {})
            parked_context["workspace_quota_admission"] = quota_payload
            parked_context["runner_claim_admission"] = claim_admission.observability
            parked_update["execution_context"] = parked_context
            parked_update["blocked_payload"] = {
                "workspace_quota_admission": quota_payload,
                "runner_claim_admission": claim_admission.observability,
            }
            await asyncio.to_thread(
                tasks_store.update_task,
                t_data.id,
                **parked_update,
            )
            await task_queue.ack_task(task_id)
            return None

        # Check per-task dependencies.
        lock_ctx = (
            t_data.execution_context
            if isinstance(t_data.execution_context, dict)
            else {}
        )
        playbook_code = lock_ctx.get("playbook_code") or t_data.pack_id or ""
        unmet = await dep_checker.check_playbook_deps(
            playbook_code,
            execution_context=lock_ctx,
        )

        if unmet:
            now_dt = datetime.now(timezone.utc)
            dep_hold = {
                "deps": unmet,
                "checked_at": now_dt.isoformat(),
            }
            parked_update = _build_parked_task_update(
                lock_ctx,
                reason="dependency_hold",
                delay_seconds=30,
                now=now_dt,
                dependency_hold=dep_hold,
                current_queue_shard=getattr(t_data, "queue_shard", None),
            )
            await asyncio.to_thread(
                tasks_store.update_task,
                t_data.id,
                **parked_update,
            )
            await task_queue.ack_task(task_id)
            return None

        # Run resource admission before lock and claim.
        playbook_metadata = resolve_installed_playbook_runner_metadata(
            playbook_code
        )
        resource_requirements = resolve_resource_requirements(
            t_data,
            execution_context=lock_ctx,
            playbook_metadata=playbook_metadata,
        )
        resource_lease_store = RedisResourceLeaseStore(task_queue)
        resource_decision = await acquire_task_resource_admission(
            task=t_data,
            requirements=resource_requirements,
            runner_profile=runner_profile,
            capacity=capacity,
            lease_store=resource_lease_store,
            owner_id=lock_owner_id,
            ttl_seconds=lock_ttl_seconds,
        )
        if not resource_decision.allow:
            resource_wait_update = build_resource_wait_task_update(
                lock_ctx,
                resource_decision,
                current_queue_shard=getattr(t_data, "queue_shard", None),
            )
            await asyncio.to_thread(
                tasks_store.update_task,
                t_data.id,
                **resource_wait_update,
            )
            await task_queue.ack_task(task_id)
            return None

        if resource_decision.execution_context_updates:
            lock_ctx = {
                **lock_ctx,
                **resource_decision.execution_context_updates,
            }
            await asyncio.to_thread(
                tasks_store.update_task,
                t_data.id,
                execution_context=lock_ctx,
            )

        # Acquire concurrency locks before claim.
        lock_keys = _resolve_lock_keys(
            lock_ctx,
            t_data.pack_id,
            persisted_concurrency_key=getattr(t_data, "concurrency_key", None),
        )
        lock_key = lock_keys[0] if lock_keys else None
        if lock_keys:
            db_conflict = await asyncio.to_thread(
                tasks_store.has_running_concurrency_conflict,
                t_data.id,
                lock_keys,
            )
            if db_conflict:
                if resource_lease_store and resource_decision:
                    await release_acquired_resource_leases(
                        resource_lease_store,
                        resource_decision.acquired_leases,
                        owner_id=lock_owner_id,
                    )
                parked_update = _build_parked_task_update(
                    lock_ctx,
                    reason="concurrency_locked",
                    delay_seconds=30,
                    now=_utc_now(),
                    lock_key=lock_key,
                    conflicting_lock_key=lock_key,
                    current_queue_shard=getattr(t_data, "queue_shard", None),
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    t_data.id,
                    **parked_update,
                )
                await task_queue.ack_task(task_id)
                return None

        if lock_keys:
            acquired_keys: list[str] = []
            conflicting_key: Optional[str] = None
            for candidate_key in lock_keys:
                acquired = await redis_queue.acquire_lock(
                    candidate_key, lock_owner_id, ttl_seconds=lock_ttl_seconds
                )
                if not acquired:
                    conflicting_key = candidate_key
                    break
                acquired_keys.append(candidate_key)

            if conflicting_key:
                for acquired_key in reversed(acquired_keys):
                    try:
                        await redis_queue.release_lock(acquired_key, lock_owner_id)
                    except Exception:
                        pass
                if resource_lease_store and resource_decision:
                    await release_acquired_resource_leases(
                        resource_lease_store,
                        resource_decision.acquired_leases,
                        owner_id=lock_owner_id,
                    )
                parked_update = _build_parked_task_update(
                    lock_ctx,
                    reason="concurrency_locked",
                    delay_seconds=30,
                    now=_utc_now(),
                    lock_key=lock_key,
                    conflicting_lock_key=conflicting_key,
                    current_queue_shard=getattr(t_data, "queue_shard", None),
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    t_data.id,
                    **parked_update,
                )
                await task_queue.ack_task(task_id)
                return None

        # Claim only pending rows.
        claimed = await asyncio.to_thread(
            tasks_store.try_claim_task,
            t_data.id,
            runner_id=runner_id,
            concurrency_keys=lock_keys,
            workspace_quota_decision=workspace_quota_decision,
        )
        if not claimed:
            db_conflict = False
            if lock_keys:
                db_conflict = await asyncio.to_thread(
                    tasks_store.has_running_concurrency_conflict,
                    t_data.id,
                    lock_keys,
                )
            logger.warning(
                f"[Worker] DB claim failed for Task {task_id}. Evaluating conflict/quota before queue acknowledgement."
            )
            for held_key in lock_keys:
                try:
                    await redis_queue.release_lock(held_key, lock_owner_id)
                except Exception:
                    pass
            if resource_lease_store and resource_decision:
                await release_acquired_resource_leases(
                    resource_lease_store,
                    resource_decision.acquired_leases,
                    owner_id=lock_owner_id,
                )
            if not db_conflict:
                try:
                    from backend.app.services.host_resources.workspace_quota_admission import (
                        decide_workspace_quota_admission_for_task,
                    )

                    post_claim_quota_decision = await asyncio.to_thread(
                        decide_workspace_quota_admission_for_task,
                        t_data,
                    )
                except Exception:
                    post_claim_quota_decision = None
                post_claim_admission = decide_runner_claim_admission(
                    t_data,
                    runner_profile,
                    db_budget,
                    resource_snapshot,
                    workspace_quota_decision=post_claim_quota_decision,
                )
                if (
                    not post_claim_admission.allow
                    and post_claim_admission.action == "park"
                ):
                    quota_payload = (
                        post_claim_admission.workspace_quota_payload or {}
                    )
                    parked_update = _build_parked_task_update(
                        lock_ctx,
                        reason=post_claim_admission.reason,
                        delay_seconds=max(
                            1,
                            post_claim_admission.delay_seconds or 10,
                        ),
                        now=_utc_now(),
                        current_queue_shard=getattr(t_data, "queue_shard", None),
                    )
                    parked_context = dict(
                        parked_update.get("execution_context") or {}
                    )
                    parked_context["workspace_quota_admission"] = quota_payload
                    parked_context["runner_claim_admission"] = (
                        post_claim_admission.observability
                    )
                    parked_update["execution_context"] = parked_context
                    parked_update["blocked_payload"] = {
                        "workspace_quota_admission": quota_payload,
                        "runner_claim_admission": post_claim_admission.observability,
                    }
                    await asyncio.to_thread(
                        tasks_store.update_task,
                        t_data.id,
                        **parked_update,
                    )
                    await task_queue.ack_task(task_id)
                    return None
            if db_conflict:
                parked_update = _build_parked_task_update(
                    lock_ctx,
                    reason="concurrency_locked",
                    delay_seconds=30,
                    now=_utc_now(),
                    lock_key=lock_key,
                    conflicting_lock_key=lock_key,
                    current_queue_shard=getattr(t_data, "queue_shard", None),
                )
                await asyncio.to_thread(
                    tasks_store.update_task,
                    t_data.id,
                    **parked_update,
                )
            await task_queue.ack_task(task_id)
            return None

        # Dispatch execution.
        task_coro = _run_single_task(
            tasks_store,
            runner_id,
            t_data.id,
            redis_queue=task_queue,
            lock_owner_id=lock_owner_id,
        )
        dispatch_task = asyncio.create_task(task_coro)
        setattr(dispatch_task, "_mindscape_pack_id", str(t_data.pack_id or ""))
        return dispatch_task

    except Exception as e:
        if db_recovery_backoff.note_failure(e):
            logger.warning(
                "Runner task dispatch deferred while PostgreSQL is recovering task_id=%s delay=%ss",
                task_id,
                db_recovery_backoff.delay_seconds,
            )
        else:
            logger.warning(
                f"Runner task dispatch error for {task_id}: {e}", exc_info=True
            )
        if resource_lease_store and resource_decision:
            try:
                await release_acquired_resource_leases(
                    resource_lease_store,
                    resource_decision.acquired_leases,
                    owner_id=lock_owner_id,
                )
            except Exception:
                pass
        # Failsafe in case of dispatch crash
        await (task_queue or redis_queue).nack_task_to_delayed(
            task_id,
            delay_sec=(
                db_recovery_backoff.delay_seconds
                if db_recovery_backoff.is_active()
                else 15
            ),
        )

    return None
