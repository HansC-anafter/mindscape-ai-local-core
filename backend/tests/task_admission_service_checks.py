from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.task_admission_service import (
    AdmissionPressure,
    TaskAdmissionService,
)


def _build_task(
    *,
    visibility: str = "background",
    auto_triggered: bool = True,
    pack_id: str = "ig_analyze_pinned_reference",
    queue_shard: str = "vision_local",
    producer_kind: str = "pin_reference",
) -> Task:
    return Task(
        id=f"task-{visibility}",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id=f"exec-{visibility}",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard=queue_shard,
        created_at=_utc_now(),
        execution_context={
            "auto_triggered": auto_triggered,
            "admission_policy": {
                "mode": "auto" if auto_triggered else "manual",
                "visibility": visibility,
                "producer_kind": producer_kind,
            },
        },
    )


class _SqliteTasksStore:
    def __init__(self) -> None:
        self._engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        blocked_reason TEXT,
                        queue_shard TEXT,
                        created_at TIMESTAMP NOT NULL,
                        next_eligible_at TIMESTAMP,
                        frontier_state TEXT,
                        frontier_enqueued_at TIMESTAMP
                    )
                    """
                )
            )

    @contextmanager
    def get_connection(self):
        with self._engine.begin() as conn:
            yield conn

    def insert_rows(self, *rows: dict) -> None:
        with self._engine.begin() as conn:
            for row in rows:
                conn.execute(
                    text(
                        """
                        INSERT INTO tasks (
                            id,
                            task_type,
                            status,
                            blocked_reason,
                            queue_shard,
                            created_at,
                            next_eligible_at,
                            frontier_state,
                            frontier_enqueued_at
                        ) VALUES (
                            :id,
                            :task_type,
                            :status,
                            :blocked_reason,
                            :queue_shard,
                            :created_at,
                            :next_eligible_at,
                            :frontier_state,
                            :frontier_enqueued_at
                        )
                        """
                    ),
                    row,
                )


def _task_row(
    *,
    task_id: str,
    status: str,
    created_at,
    queue_shard: str = "browser_local",
    blocked_reason: str | None = None,
    next_eligible_at=None,
    frontier_state: str | None = None,
    frontier_enqueued_at=None,
) -> dict:
    return {
        "id": task_id,
        "task_type": "playbook_execution",
        "status": status,
        "blocked_reason": blocked_reason,
        "queue_shard": queue_shard,
        "created_at": created_at,
        "next_eligible_at": next_eligible_at or created_at,
        "frontier_state": frontier_state,
        "frontier_enqueued_at": frontier_enqueued_at,
    }


def test_manual_task_bypasses_admission_defer(monkeypatch):
    service = TaskAdmissionService()
    task = _build_task(auto_triggered=False)

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
    task = _build_task()

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
    background_task = _build_task(visibility="background")
    visible_task = _build_task(visibility="visible")

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
    store = _SqliteTasksStore()
    now = _utc_now()
    ready_frontier_at = now - timedelta(seconds=20)

    store.insert_rows(
        _task_row(
            task_id="ready-task",
            status="pending",
            created_at=now - timedelta(hours=2),
            next_eligible_at=ready_frontier_at,
            frontier_state="ready",
            frontier_enqueued_at=ready_frontier_at,
        ),
        _task_row(
            task_id="cold-concurrency-locked",
            status="pending",
            created_at=now - timedelta(hours=8),
            next_eligible_at=now - timedelta(minutes=5),
            blocked_reason="concurrency_locked",
            frontier_state="cold",
        ),
        _task_row(
            task_id="cold-admission-deferred",
            status="pending",
            created_at=now - timedelta(hours=6),
            next_eligible_at=now - timedelta(minutes=5),
            blocked_reason="admission_deferred",
            frontier_state="cold",
        ),
        _task_row(
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
    store = _SqliteTasksStore()
    now = _utc_now()

    store.insert_rows(
        _task_row(
            task_id="cold-follow-1",
            status="pending",
            created_at=now - timedelta(hours=9),
            next_eligible_at=now - timedelta(hours=8),
            blocked_reason="concurrency_locked",
            frontier_state="cold",
        ),
        _task_row(
            task_id="cold-follow-2",
            status="pending",
            created_at=now - timedelta(hours=7),
            next_eligible_at=now - timedelta(hours=6),
            blocked_reason="concurrency_locked",
            frontier_state="cold",
        ),
        _task_row(
            task_id="running-follow",
            status="running",
            created_at=now - timedelta(minutes=10),
            frontier_state="running",
        ),
    )

    task = _build_task(
        visibility="visible",
        pack_id="ig_batch_pin_references",
        queue_shard="browser_local",
        producer_kind="after_visit",
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv(
        "LOCAL_CORE_TASK_ADMISSION_BROWSER_LOCAL_OLDEST_PENDING_AGE_SECONDS",
        "1",
    )

    decision = service.evaluate_on_create(store, task)

    assert decision.allow is True


def test_load_queue_pressure_accepts_legacy_alias_rows_under_canonical_partition():
    service = TaskAdmissionService()
    store = _SqliteTasksStore()
    now = _utc_now()

    store.insert_rows(
        _task_row(
            task_id="legacy-browser-task",
            status="pending",
            created_at=now - timedelta(minutes=5),
            queue_shard="ig_browser",
            frontier_state="ready",
        ),
        _task_row(
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
