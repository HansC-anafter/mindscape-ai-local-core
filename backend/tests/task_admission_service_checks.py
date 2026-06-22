from datetime import timedelta

from backend.app.models.workspace import _utc_now
from backend.app.services.task_admission_service import (
    AdmissionPressure,
    TaskAdmissionService,
)
from backend.app.services.task_admission_pressure_scope import (
    resolve_admission_pressure_scope,
)
from backend.tests.task_admission_service_support import (
    MemoryTasksStore,
    build_task,
    task_row,
)


def test_manual_task_bypasses_admission_defer(monkeypatch):
    service = TaskAdmissionService()
    task = build_task(auto_triggered=False)

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setattr(
        service,
        "_load_queue_pressure",
        lambda *_args, **_kwargs: AdmissionPressure(
            queue_shard="vision_local",
            pending_total=999,
            running_total=4,
            oldest_pending_at=_utc_now() - timedelta(hours=1),
        ),
    )

    decision = service.evaluate_on_create(object(), task)

    assert decision.allow is True


def test_auto_task_deferred_when_shard_over_budget(monkeypatch):
    service = TaskAdmissionService()
    task = build_task()

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_PENDING_LIMIT", "10")
    monkeypatch.setattr(
        service,
        "_load_queue_pressure",
        lambda *_args, **_kwargs: AdmissionPressure(
            queue_shard="vision_local",
            pending_total=25,
            running_total=2,
            oldest_pending_at=_utc_now() - timedelta(seconds=10),
        ),
    )

    decision = service.evaluate_on_create(object(), task)

    assert decision.allow is False
    assert decision.next_eligible_at is not None
    assert decision.blocked_payload["reason"] == "pending_limit"
    assert decision.execution_context["admission"]["state"] == "deferred"
    assert (
        decision.execution_context["resume_after"]
        == decision.next_eligible_at.isoformat()
    )


def test_visible_auto_ranks_above_background_auto(monkeypatch):
    service = TaskAdmissionService()
    background_task = build_task(visibility="background")
    visible_task = build_task(visibility="visible")

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_PENDING_LIMIT", "100")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_BACKGROUND_PENDING_LIMIT_MULTIPLIER", "1")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_VISIBLE_PENDING_LIMIT_MULTIPLIER", "2")
    monkeypatch.setattr(
        service,
        "_load_queue_pressure",
        lambda *_args, **_kwargs: AdmissionPressure(
            queue_shard="vision_local",
            pending_total=150,
            running_total=1,
            oldest_pending_at=None,
        ),
    )

    background_decision = service.evaluate_on_create(object(), background_task)
    visible_decision = service.evaluate_on_create(object(), visible_task)

    assert background_decision.allow is False
    assert visible_decision.allow is True


def test_load_queue_pressure_ignores_cold_parked_backlog():
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()
    ready_frontier_at = now - timedelta(seconds=20)

    store.insert_rows(
        task_row(
            task_id="ready-task",
            status="pending",
            created_at=now - timedelta(hours=2),
            next_eligible_at=ready_frontier_at,
            frontier_state="ready",
            frontier_enqueued_at=ready_frontier_at,
        ),
        task_row(
            task_id="cold-concurrency-locked",
            status="pending",
            created_at=now - timedelta(hours=8),
            next_eligible_at=now - timedelta(minutes=5),
            blocked_reason="concurrency_locked",
            frontier_state="cold",
        ),
        task_row(
            task_id="cold-admission-deferred",
            status="pending",
            created_at=now - timedelta(hours=6),
            next_eligible_at=now - timedelta(minutes=5),
            blocked_reason="admission_deferred",
            frontier_state="cold",
        ),
        task_row(
            task_id="running-task",
            status="running",
            created_at=now - timedelta(minutes=2),
            frontier_state="running",
        ),
    )

    pressure = service._load_queue_pressure(store, "browser_local")

    assert pressure.pending_total == 1
    assert pressure.running_total == 1
    assert pressure.oldest_pending_at is not None
    assert abs((pressure.oldest_pending_at - ready_frontier_at).total_seconds()) < 1


def test_after_visit_visible_task_bypasses_cold_concurrency_locked_age_pressure(monkeypatch):
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()

    store.insert_rows(
        task_row(
            task_id="cold-follow-1",
            status="pending",
            created_at=now - timedelta(hours=9),
            next_eligible_at=now - timedelta(hours=8),
            blocked_reason="concurrency_locked",
            frontier_state="cold",
        ),
        task_row(
            task_id="cold-follow-2",
            status="pending",
            created_at=now - timedelta(hours=7),
            next_eligible_at=now - timedelta(hours=6),
            blocked_reason="concurrency_locked",
            frontier_state="cold",
        ),
        task_row(
            task_id="running-follow",
            status="running",
            created_at=now - timedelta(minutes=10),
            frontier_state="running",
        ),
    )

    task = build_task(
        visibility="visible",
        pack_id="ig_batch_pin_references",
        queue_shard="default_local_browser",
        producer_kind="after_visit",
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv(
        "LOCAL_CORE_TASK_ADMISSION_BROWSER_LOCAL_OLDEST_PENDING_AGE_SECONDS",
        "1",
    )

    decision = service.evaluate_on_create(store, task)

    assert decision.allow is True


def test_managed_browser_batch_pressure_uses_fairness_lane(monkeypatch):
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()
    old_ready_at = now - timedelta(minutes=10)

    store.insert_rows(
        task_row(
            task_id="old-batch-ready",
            pack_id="ig_batch_pin_references",
            status="pending",
            created_at=now - timedelta(hours=2),
            queue_shard="default_local_browser",
            next_eligible_at=old_ready_at,
            frontier_state="ready",
            frontier_enqueued_at=old_ready_at,
            execution_context={
                "playbook_code": "ig_batch_pin_references",
                "task_family": "browser_batch",
                "resource_class": "browser",
                "fairness_lane_key": "ig_batch_pin_references",
            },
        ),
        task_row(
            task_id="running-batch",
            pack_id="ig_batch_pin_references",
            status="running",
            created_at=now - timedelta(minutes=3),
            queue_shard="default_local_browser",
            frontier_state="running",
            execution_context={
                "playbook_code": "ig_batch_pin_references",
                "task_family": "browser_batch",
                "resource_class": "browser",
                "fairness_lane_key": "ig_batch_pin_references",
            },
        ),
    )
    task = build_task(
        visibility="visible",
        pack_id="ig_pin_post_detail",
        queue_shard="default_local_browser",
        producer_kind="batch_pin_carousel_orchestrator",
    )
    task.execution_context.update(
        {
            "task_family": "browser_batch",
            "resource_class": "browser",
            "fairness_lane_key": "ig_pin_post_detail",
            "managed_runner_role": "managed_browser_batch",
        }
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv(
        "LOCAL_CORE_TASK_ADMISSION_DEFAULT_LOCAL_BROWSER_OLDEST_PENDING_AGE_SECONDS",
        "1",
    )

    decision = service.evaluate_on_release(store, task)
    pressure = service._load_queue_pressure(
        store,
        "default_local_browser",
        pressure_scope=resolve_admission_pressure_scope(
            task,
            queue_shard="default_local_browser",
        ),
    )

    assert decision.allow is True
    assert pressure.pending_total == 0
    assert pressure.running_total == 0
    assert pressure.scope_name == "browser_fairness_lane:ig_pin_post_detail"


def test_managed_browser_batch_pressure_keeps_same_lane_backpressure(monkeypatch):
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()
    old_ready_at = now - timedelta(minutes=10)

    store.insert_rows(
        task_row(
            task_id="old-detail-ready",
            pack_id="ig_pin_post_detail",
            status="pending",
            created_at=now - timedelta(hours=2),
            queue_shard="default_local_browser",
            next_eligible_at=old_ready_at,
            frontier_state="ready",
            frontier_enqueued_at=old_ready_at,
            execution_context={
                "playbook_code": "ig_pin_post_detail",
                "task_family": "browser_batch",
                "resource_class": "browser",
                "fairness_lane_key": "ig_pin_post_detail",
            },
        )
    )
    task = build_task(
        visibility="visible",
        pack_id="ig_pin_post_detail",
        queue_shard="default_local_browser",
        producer_kind="batch_pin_carousel_orchestrator",
    )
    task.execution_context.update(
        {
            "task_family": "browser_batch",
            "resource_class": "browser",
            "fairness_lane_key": "ig_pin_post_detail",
            "managed_runner_role": "managed_browser_batch",
        }
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv(
        "LOCAL_CORE_TASK_ADMISSION_DEFAULT_LOCAL_BROWSER_OLDEST_PENDING_AGE_SECONDS",
        "1",
    )

    decision = service.evaluate_on_release(store, task)

    assert decision.allow is False
    assert decision.blocked_payload["reason"] == "oldest_pending_age"
    assert (
        decision.blocked_payload["pressure"]["scope"]
        == "browser_fairness_lane:ig_pin_post_detail"
    )


def test_load_queue_pressure_accepts_legacy_alias_rows_under_canonical_partition():
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()

    store.insert_rows(
        task_row(
            task_id="legacy-browser-task",
            status="pending",
            created_at=now - timedelta(minutes=5),
            queue_shard="ig_browser",
            frontier_state="ready",
        ),
        task_row(
            task_id="legacy-browser-running",
            status="running",
            created_at=now - timedelta(minutes=2),
            queue_shard="ig_browser",
            frontier_state="running",
        ),
    )

    pressure = service._load_queue_pressure(store, "browser_local")

    assert pressure.pending_total == 1
    assert pressure.running_total == 1


def test_resolve_limits_accepts_legacy_alias_env_names(monkeypatch):
    service = TaskAdmissionService()
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_IG_BROWSER_PENDING_LIMIT", "17")

    limits = service._resolve_limits("browser_local", "background")

    assert limits.pending_limit == 17


def test_single_flight_defers_same_playbook_key_when_ready_task_exists(monkeypatch):
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()
    key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_rows(
        task_row(
            task_id="ready-existing",
            status="pending",
            created_at=now,
            queue_shard="vision_local",
            concurrency_key=key,
            frontier_state="ready",
        )
    )
    task = build_task(
        task_id="new-task",
        queue_shard="vision_local",
        concurrency_key=key,
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    decision = service.evaluate_on_create(store, task)

    assert decision.allow is False
    assert decision.blocked_payload["policy"] == "single_flight_admission"
    assert decision.blocked_payload["reason"] == "active_window"
    assert decision.blocked_payload["conflict_task_id"] == "ready-existing"
    assert decision.execution_context["admission"]["state"] == "deferred"
    assert store.single_flight_queries == ["running", "pending"]


def test_single_flight_allows_different_playbook_key(monkeypatch):
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()
    store.insert_rows(
        task_row(
            task_id="ready-existing",
            status="pending",
            created_at=now,
            queue_shard="vision_local",
            concurrency_key="concurrency:playbook:other",
            frontier_state="ready",
        )
    )
    task = build_task(
        task_id="new-task",
        queue_shard="vision_local",
        concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    decision = service.evaluate_on_create(store, task)

    assert decision.allow is True


def test_single_flight_release_keeps_task_cold_when_same_key_running(monkeypatch):
    service = TaskAdmissionService()
    store = MemoryTasksStore()
    now = _utc_now()
    key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_rows(
        task_row(
            task_id="running-existing",
            status="running",
            created_at=now,
            queue_shard="vision_local",
            concurrency_key=key,
            frontier_state="running",
        )
    )
    task = build_task(
        task_id="deferred-task",
        queue_shard="vision_local",
        concurrency_key=key,
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    decision = service.evaluate_on_release(store, task)

    assert decision.allow is False
    assert decision.blocked_payload["policy"] == "single_flight_admission"
    assert decision.blocked_payload["conflict_task_id"] == "running-existing"
    assert store.single_flight_queries == ["running"]
