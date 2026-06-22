import asyncio
from pathlib import Path

import pytest

from backend.app.runner import worker
from backend.app.runner.worker import (
    _build_parked_task_update,
    _dequeue_by_browser_fair_candidate_policy,
    _dequeue_by_route_gate_policy,
)
from backend.app.runner.database_backoff import (
    RunnerDatabaseRecoveryBackoff,
    is_database_recovery_error,
)
from backend.app.services.host_resources import route_gate
from backend.app.services.host_resources.route_identity_projection import (
    serialize_route_identity_projection,
)
from backend.tests.runner.worker_playbook_fairness_support import (
    BATCH_PLAYBOOK,
    DETAIL_PLAYBOOK,
    FOLLOWING_PLAYBOOK,
    FakeCandidateTasksStore,
    FakeFairQueue,
    browser_profile,
    candidate_projection,
    compute_profile,
    default_profile,
    projection,
)


def test_worker_browser_fairness_keeps_following_available_to_general_browser_profile():
    queue = FakeFairQueue(["task-following", "task-batch"])
    tasks_store = FakeCandidateTasksStore(
        {
            "task-following": candidate_projection(
                "task-following",
                FOLLOWING_PLAYBOOK,
            ),
            "task-batch": candidate_projection(
                "task-batch",
                BATCH_PLAYBOOK,
            ),
        },
        {
            FOLLOWING_PLAYBOOK: 0,
            BATCH_PLAYBOOK: 1,
        },
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_browser_fair_candidate_policy(
            [queue],
            tasks_store=tasks_store,
            runner_profile=browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id == "task-following"
    assert queue_store is queue
    assert drain_wait is False
    assert queue.promoted == ["task-following"]
    assert tasks_store.requested_ids == ["task-following", "task-batch"]


def test_route_gate_policy_falls_back_when_only_same_playbook():
    queue = FakeFairQueue(["task-batch-a", "task-batch-b"])
    for task_id in ["task-batch-a", "task-batch-b"]:
        queue.client.projections[
            f"mindscape:host_resources:route_identity:{task_id}"
        ] = serialize_route_identity_projection(
            task_id,
            projection(task_id, BATCH_PLAYBOOK),
        )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_route_gate_policy(
            [queue],
            runner_profile=browser_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
            active_pack_ids={BATCH_PLAYBOOK},
        )
    )

    assert task_id is None
    assert queue_store is None
    assert drain_wait is False
    assert queue.promoted == []


def test_route_gate_policy_ignores_unrelated_drain_after_current(monkeypatch):
    queue = FakeFairQueue(["task-default"], pack_id="default_local_browser")
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-default"
    ] = serialize_route_identity_projection(
        "task-default",
        projection("task-default", BATCH_PLAYBOOK),
    )
    monkeypatch.setattr(
        route_gate,
        "list_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation"],
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_route_gate_policy(
            [queue],
            runner_profile=default_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
            active_pack_ids=set(),
        )
    )

    assert task_id is None
    assert queue_store is None
    assert drain_wait is False
    assert queue.promoted == []


def test_worker_browser_fairness_ignores_unrelated_drain_after_current(monkeypatch):
    monkeypatch.setattr(
        route_gate,
        "get_active_route_reservations",
        lambda: [
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                    "resource_groups": ["mps_generation"],
                    "resource_flavor": "local.mps.comfyui",
                    "drain_policy": "drain_after_current",
                },
            }
        ],
    )
    queue = FakeFairQueue(
        ["task-batch", "task-pin"],
        pack_id="default_local_browser",
    )
    tasks_store = FakeCandidateTasksStore(
        {
            "task-batch": candidate_projection(
                "task-batch",
                BATCH_PLAYBOOK,
            ),
            "task-pin": candidate_projection(
                "task-pin",
                DETAIL_PLAYBOOK,
            ),
        },
        {
            BATCH_PLAYBOOK: 1,
            DETAIL_PLAYBOOK: 0,
        },
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_browser_fair_candidate_policy(
            [queue],
            tasks_store=tasks_store,
            runner_profile=default_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id == "task-pin"
    assert queue_store is queue
    assert drain_wait is False
    assert queue.promoted == ["task-pin"]


def test_worker_browser_fairness_uses_db_running_counts_before_fifo(monkeypatch):
    monkeypatch.setattr(route_gate, "get_active_route_reservations", lambda: [])
    queue = FakeFairQueue(
        ["task-batch", "task-pin"],
        pack_id="default_local_browser",
    )
    tasks_store = FakeCandidateTasksStore(
        {
            "task-batch": candidate_projection(
                "task-batch",
                BATCH_PLAYBOOK,
            ),
            "task-pin": candidate_projection(
                "task-pin",
                DETAIL_PLAYBOOK,
            ),
        },
        {
            BATCH_PLAYBOOK: 1,
            DETAIL_PLAYBOOK: 0,
        },
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_browser_fair_candidate_policy(
            [queue],
            tasks_store=tasks_store,
            runner_profile=default_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id == "task-pin"
    assert queue_store is queue
    assert drain_wait is False
    assert queue.promoted == ["task-pin"]
    assert tasks_store.requested_ids == ["task-batch", "task-pin"]


def test_worker_browser_fairness_uses_db_projection_when_route_projection_missing(
    monkeypatch,
):
    monkeypatch.setattr(route_gate, "get_active_route_reservations", lambda: [])
    queue = FakeFairQueue(["task-batch"], pack_id="default_local_browser")
    tasks_store = FakeCandidateTasksStore(
        {
            "task-batch": candidate_projection(
                "task-batch",
                BATCH_PLAYBOOK,
            ),
        },
        {
            BATCH_PLAYBOOK: 0,
        },
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_browser_fair_candidate_policy(
            [queue],
            tasks_store=tasks_store,
            runner_profile=default_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id == "task-batch"
    assert queue_store is queue
    assert drain_wait is False
    assert queue.promoted == ["task-batch"]


def test_worker_non_browser_keeps_existing_fifo_path(monkeypatch):
    monkeypatch.setattr(route_gate, "get_active_route_reservations", lambda: [])
    queue = FakeFairQueue(["task-default"], pack_id="default_local_browser")
    tasks_store = FakeCandidateTasksStore(
        {"task-default": candidate_projection("task-default", BATCH_PLAYBOOK)},
        {BATCH_PLAYBOOK: 0},
    )

    task_id, queue_store, drain_wait = asyncio.run(
        _dequeue_by_browser_fair_candidate_policy(
            [queue],
            tasks_store=tasks_store,
            runner_profile=compute_profile(),
            visibility_timeout_sec=180,
            scan_limit=10,
        )
    )

    assert task_id is None
    assert queue_store is None
    assert drain_wait is False
    assert queue.promoted == []


def test_managed_batch_runner_and_spillover_compose_semantics():
    compose_path = next(
        (
            candidate
            for candidate in [
                Path(__file__).resolve().parents[3] / "docker-compose.yml",
                Path(__file__).resolve().parents[4] / "docker-compose.yml",
            ]
            if candidate.is_file()
        ),
        None,
    )
    if compose_path is None:
        pytest.skip("docker-compose.yml is not mounted in this test container")
    compose_text = compose_path.read_text(encoding="utf-8")

    assert "LOCAL_CORE_RUNNER_RESERVED_PACK_SLOTS" not in compose_text
    assert "runner-default-local-browser:" in compose_text
    assert "runner-browser-extra:" in compose_text
    assert "runner-default:" not in compose_text
    assert "IG_THUMBNAIL_BROWSER_FALLBACK_MAX_INFLIGHT" not in compose_text
    assert "LOCAL_CORE_RUNNER_DEFAULT_LOCAL_BROWSER_ACCEPTED_CAPABILITY_CODES" not in compose_text
    assert "LOCAL_CORE_RUNNER_VISION_MLX_DEV_ACCEPTED_CAPABILITY_CODES" not in compose_text
    assert "LOCAL_CORE_RUNNER_DEFAULT_LOCAL_BROWSER_MAX_INFLIGHT:-3" in compose_text
    assert "LOCAL_CORE_RUNNER_SPILLOVER_PROFILE:-default_local" in compose_text
    assert "LOCAL_CORE_RUNNER_SPILLOVER_ACCEPTED_RESOURCE_CLASSES:-compute,api" in compose_text
    assert "LOCAL_CORE_RUNNER_SPILLOVER_MAX_INFLIGHT:-1" in compose_text


def test_database_recovery_error_detection_and_backoff():
    exc = RuntimeError(
        'connection to server at "postgres" failed: FATAL:  the database system is not yet accepting connections'
    )
    backoff = RunnerDatabaseRecoveryBackoff(delay_seconds=5)

    assert is_database_recovery_error(exc) is True
    assert backoff.note_failure(exc) is True
    assert backoff.is_active() is True
    assert backoff.remaining_seconds() > 0


def test_parked_pending_update_clears_live_runner_ownership():
    update = _build_parked_task_update(
        {
            "playbook_code": BATCH_PLAYBOOK,
            "runner_id": "runner-old",
            "heartbeat_at": "2026-05-08T03:00:00+00:00",
        },
        reason="concurrency_locked",
        delay_seconds=30,
        lock_key="profile:source:a",
        conflicting_lock_key="profile:source:a",
        current_queue_shard="default_local_browser",
    )

    ctx = update["execution_context"]
    assert ctx["last_runner_id"] == "runner-old"
    assert "runner_id" not in ctx
    assert "heartbeat_at" not in ctx
    assert update["frontier_state"] == "cold"
    assert update["queue_shard"] == "default_local_browser"


def test_runner_lock_ttl_uses_runtime_configuration(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", "3600")

    assert worker._runner_lock_ttl_seconds() == 3600
