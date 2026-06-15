"""Runner worker compatibility facade and CLI entrypoint."""

import asyncio
import logging
import os

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.runner_topology import runner_profile_can_claim_task
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.runner.utils import _utc_now, _parse_utc_iso, _env_int
from backend.app.runner.concurrency import (
    _runner_id,
    _resolve_lock_key,
    _resolve_lock_keys,
    _build_inputs,
)
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.reaper import (
    _request_watchdog_abort_for_no_progress_tasks,
    _reap_stale_running_tasks,
    _reap_redis_queues,
)
from backend.app.runner.task_executor import (
    _child_execute_playbook,
    _initialize_capability_packages_for_runner,
    _run_single_task,
)
from backend.app.runner.restart import (
    _check_restart_sentinel,
    _RESTART_SENTINEL_PATH,
    _RESTART_DRAIN_TIMEOUT_SECONDS,
)
from backend.app.runner.db_pool_pressure import check_db_pool_pressure
from backend.app.runner.worker_startup import (
    _backfill_pending_to_redis,
    _load_active_runner_ids,
    _postgres_runner_heartbeat_enabled,
    _purge_task_ids_from_transport,
    _reset_orphaned_running_tasks,
    _runner_lock_ttl_seconds,
)
from backend.app.runner.worker_transport import (
    _build_ready_queue_stores,
    _collect_transport_members,
    _dequeue_from_ready_queues,
    _normalize_task_id,
    _pending_task_runnable_from_queue,
    _repair_misqueued_task_if_needed,
    _resolve_task_queue_shard,
    _split_ready_target,
)
from backend.app.runner.worker_claim_policy import (
    _build_parked_task_update,
    _dequeue_by_browser_fair_candidate_policy,
    _dequeue_by_route_gate_policy,
    _host_route_gate_enabled,
    _route_drain_after_current_status,
    _runner_claim_gate_paused,
    _runner_claim_gate_status,
)
from backend.app.runner.worker_maintenance import (
    _cleanup_stale_locks,
    _maintenance_loop,
    _run_maintenance_cycle,
)
from backend.app.runner.worker_loop import run_forever

logger = logging.getLogger(__name__)

__all__ = [
    "_utc_now",
    "_parse_utc_iso",
    "_env_int",
    "_runner_id",
    "_resolve_lock_key",
    "_resolve_lock_keys",
    "_build_inputs",
    "_invoke_on_fail_hook",
    "_request_watchdog_abort_for_no_progress_tasks",
    "_reap_stale_running_tasks",
    "_reap_redis_queues",
    "_child_execute_playbook",
    "_initialize_capability_packages_for_runner",
    "_run_single_task",
    "_check_restart_sentinel",
    "_RESTART_SENTINEL_PATH",
    "_RESTART_DRAIN_TIMEOUT_SECONDS",
    "_runner_lock_ttl_seconds",
    "_postgres_runner_heartbeat_enabled",
    "_load_active_runner_ids",
    "_reset_orphaned_running_tasks",
    "_purge_task_ids_from_transport",
    "_backfill_pending_to_redis",
    "_resolve_task_queue_shard",
    "_build_ready_queue_stores",
    "_split_ready_target",
    "_normalize_task_id",
    "_collect_transport_members",
    "_dequeue_from_ready_queues",
    "_repair_misqueued_task_if_needed",
    "_pending_task_runnable_from_queue",
    "_host_route_gate_enabled",
    "_runner_claim_gate_status",
    "_runner_claim_gate_paused",
    "_route_drain_after_current_status",
    "_dequeue_by_route_gate_policy",
    "_dequeue_by_browser_fair_candidate_policy",
    "_build_parked_task_update",
    "_cleanup_stale_locks",
    "_run_maintenance_cycle",
    "_maintenance_loop",
    "run_forever",
    "main",
]


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    _initialize_capability_packages_for_runner()
    try:
        store = MindscapeStore()
        tasks_store = TasksStore()
        rid = _runner_id()
        _reap_stale_running_tasks(
            tasks_store,
            runner_id=rid,
            redis_queue=RedisRunnerQueueStore(),
        )

    except Exception:
        pass
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
