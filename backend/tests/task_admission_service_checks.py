from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.runner_topology import queue_partition_matches
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
    task_id: str | None = None,
    concurrency_key: str | None = None,
) -> Task:
    return Task(
        id=task_id or f"task-{visibility}",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id=f"exec-{visibility}",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard=queue_shard,
        concurrency_key=concurrency_key,
        created_at=_utc_now(),
        execution_context={
            "auto_triggered": auto_triggered,
            "playbook_code": pack_id,
            "concurrency": {
                "lock_scope": "playbook",
                "max_parallel": 1,
            },
            "admission_policy": {
                "mode": "auto" if auto_triggered else "manual",
                "visibility": visibility,
                "producer_kind": producer_kind,
            },
        },
    )


class _MemoryTasksStore:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.single_flight_queries: list[str] = []

    @contextmanager
    def get_connection(self):
        yield _MemoryTaskPressureConnection(self.rows, self.single_flight_queries)

    def insert_rows(self, *rows: dict) -> None:
        self.rows.extend(dict(row) for row in rows)


class _MemoryTaskPressureResult:
    def __init__(self, row: SimpleNamespace) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _MemoryTaskPressureConnection:
    def __init__(self, rows: list[dict], single_flight_queries: list[str]) -> None:
        self.rows = rows
        self.single_flight_queries = single_flight_queries

    def execute(self, query, params):
        query_text = str(query)
        if "concurrency_key = :concurrency_key" in query_text:
            query_kind = (
                "pending" if "status = :pending_status" in query_text else "running"
            )
            self.single_flight_queries.append(query_kind)
            return _MemoryTaskPressureResult(
                self._single_flight_conflict(params, query_kind)
            )
        if "pending_total" in query_text:
            return _MemoryTaskPressureResult(self._pending_pressure(params))
        if "running_total" in query_text:
            return _MemoryTaskPressureResult(self._running_pressure(params))
        raise AssertionError(f"Unexpected pressure query: {query_text}")

    def _matches_queue(self, row: dict, params: dict) -> bool:
        queue_shard = row.get("queue_shard")
        expected = params.get("queue_partition_0")
        return queue_partition_matches(queue_shard, expected)

    def _pending_pressure(self, params: dict) -> SimpleNamespace:
        now = params["now"]
        pending_rows = [
            row
            for row in self.rows
            if row.get("task_type")
            in {params["task_type_pb"], params["task_type_tool"]}
            and row.get("status") == params["pending_status"]
            and (row.get("blocked_reason") in {None, params["unblocked_reason"]})
            and row.get("next_eligible_at") <= now
            and row.get("frontier_state") == params["ready_frontier_state"]
            and self._matches_queue(row, params)
        ]
        oldest = None
        if pending_rows:
            oldest = min(
                row.get("frontier_enqueued_at")
                or row.get("next_eligible_at")
                or row.get("created_at")
                for row in pending_rows
            )
        return SimpleNamespace(
            pending_total=len(pending_rows),
            oldest_pending_at=oldest,
        )

    def _running_pressure(self, params: dict) -> SimpleNamespace:
        running_rows = [
            row
            for row in self.rows
            if row.get("task_type")
            in {params["task_type_pb"], params["task_type_tool"]}
            and row.get("status") == params["running_status"]
            and self._matches_queue(row, params)
        ]
        return SimpleNamespace(running_total=len(running_rows))

    def _single_flight_conflict(self, params: dict, query_kind: str):
        for row in sorted(self.rows, key=lambda item: (item["created_at"], item["id"])):
            if row.get("id") == params["task_id"]:
                continue
            if row.get("concurrency_key") != params["concurrency_key"]:
                continue
            if row.get("task_type") not in {
                params["task_type_pb"],
                params["task_type_tool"],
            }:
                continue
            if (
                query_kind == "running"
                and row.get("status") == params["running_status"]
                and row.get("frontier_state")
                in {None, params["running_frontier_state"]}
            ):
                return SimpleNamespace(
                    id=row.get("id"),
                    status=row.get("status"),
                    frontier_state=row.get("frontier_state"),
                )
            if query_kind == "pending" and (
                row.get("status") == params["pending_status"]
                and row.get("frontier_state")
                in {params["ready_frontier_state"], params["running_frontier_state"]}
                and row.get("blocked_reason") in {None, params["unblocked_reason"]}
                and row.get("next_eligible_at") <= params["now"]
            ):
                return SimpleNamespace(
                    id=row.get("id"),
                    status=row.get("status"),
                    frontier_state=row.get("frontier_state"),
                )
        return None


def _task_row(
    *,
    task_id: str,
    status: str,
    created_at,
    queue_shard: str = "browser_local",
    concurrency_key: str | None = None,
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
        "concurrency_key": concurrency_key,
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
    store = _MemoryTasksStore()
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
    store = _MemoryTasksStore()
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
    store = _MemoryTasksStore()
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


def test_single_flight_defers_same_playbook_key_when_ready_task_exists(monkeypatch):
    service = TaskAdmissionService()
    store = _MemoryTasksStore()
    now = _utc_now()
    key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_rows(
        _task_row(
            task_id="ready-existing",
            status="pending",
            created_at=now,
            queue_shard="vision_local",
            concurrency_key=key,
            frontier_state="ready",
        )
    )
    task = _build_task(
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
    store = _MemoryTasksStore()
    now = _utc_now()
    store.insert_rows(
        _task_row(
            task_id="ready-existing",
            status="pending",
            created_at=now,
            queue_shard="vision_local",
            concurrency_key="concurrency:playbook:other",
            frontier_state="ready",
        )
    )
    task = _build_task(
        task_id="new-task",
        queue_shard="vision_local",
        concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
    )

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    decision = service.evaluate_on_create(store, task)

    assert decision.allow is True


def test_single_flight_release_keeps_task_cold_when_same_key_running(monkeypatch):
    service = TaskAdmissionService()
    store = _MemoryTasksStore()
    now = _utc_now()
    key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_rows(
        _task_row(
            task_id="running-existing",
            status="running",
            created_at=now,
            queue_shard="vision_local",
            concurrency_key=key,
            frontier_state="running",
        )
    )
    task = _build_task(
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
