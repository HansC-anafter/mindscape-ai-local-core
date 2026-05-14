import json
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._runner import (
    _build_claim_execution_context,
    TasksStoreRunnerMixin,
)


class _SqliteClaimStore(TasksStoreRunnerMixin):
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
                        status TEXT NOT NULL,
                        params TEXT,
                        execution_context TEXT,
                        concurrency_key TEXT,
                        runner_id TEXT,
                        heartbeat_at TIMESTAMP,
                        started_at TIMESTAMP,
                        blocked_reason TEXT,
                        blocked_payload TEXT,
                        frontier_state TEXT,
                        frontier_enqueued_at TIMESTAMP
                    )
                    """
                )
            )

    @contextmanager
    def transaction(self):
        with self._engine.begin() as conn:
            yield conn

    @contextmanager
    def get_connection(self):
        with self._engine.begin() as conn:
            yield conn

    def serialize_json(self, value):
        return json.dumps(value)

    def deserialize_json(self, value, default):
        if not value:
            return default
        return json.loads(value)

    def insert_task(
        self,
        task_id: str,
        *,
        status: str,
        concurrency_key: str | None,
        params: dict | None = None,
        execution_context: dict | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id,
                        status,
                        params,
                        execution_context,
                        concurrency_key,
                        frontier_state
                    ) VALUES (
                        :id,
                        :status,
                        :params,
                        :execution_context,
                        :concurrency_key,
                        :frontier_state
                    )
                    """
                ),
                {
                    "id": task_id,
                    "status": status,
                    "params": json.dumps(params or {}),
                    "execution_context": json.dumps(execution_context or {}),
                    "concurrency_key": concurrency_key,
                    "frontier_state": "ready",
                },
            )

    def task_status(self, task_id: str) -> str:
        with self._engine.begin() as conn:
            return conn.execute(
                text("SELECT status FROM tasks WHERE id = :task_id"),
                {"task_id": task_id},
            ).scalar_one()

    def execution_context(self, task_id: str) -> dict:
        with self._engine.begin() as conn:
            raw = conn.execute(
                text("SELECT execution_context FROM tasks WHERE id = :task_id"),
                {"task_id": task_id},
            ).scalar_one()
        return json.loads(raw)


def test_claim_context_clears_stale_deferred_metadata():
    now = datetime(2026, 5, 8, 3, 30, tzinfo=timezone.utc)

    ctx = _build_claim_execution_context(
        {
            "inputs": {"target_handle": "example"},
            "retry_count": 2,
            "resource_wait_count": 1,
            "resource_pressure_source": "subprocess_sigkill",
            "resource_pressure": True,
            "resource_retry_delay_sec": 300,
            "resource_snapshot": {"memory": {"working_set_ratio": 0.91}},
            "runner_id": "old-runner",
            "heartbeat_at": "2026-05-08T03:00:00+00:00",
            "resume_after": "2026-05-08T03:05:00+00:00",
            "runner_skip_reason": "concurrency_locked",
            "error": "previous failure",
            "failed_at": "2026-05-08T03:00:01+00:00",
        },
        task_params={"target_handle": "from-params"},
        runner_id="new-runner",
        now=now,
    )

    assert ctx["inputs"] == {"target_handle": "example"}
    assert ctx["retry_count"] == 2
    assert ctx["resource_wait_count"] == 1
    assert ctx["runner_id"] == "new-runner"
    assert ctx["heartbeat_at"] == "2026-05-08T03:30:00+00:00"
    assert ctx["status"] == "running"

    for stale_key in (
        "resource_pressure_source",
        "resource_pressure",
        "resource_retry_delay_sec",
        "resource_snapshot",
        "resume_after",
        "runner_skip_reason",
        "error",
        "failed_at",
    ):
        assert stale_key not in ctx


def test_try_claim_task_blocks_existing_running_concurrency_key():
    store = _SqliteClaimStore()
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_task(
        "running-task",
        status=TaskStatus.RUNNING.value,
        concurrency_key=lock_key,
    )
    store.insert_task(
        "pending-task",
        status=TaskStatus.PENDING.value,
        concurrency_key=lock_key,
    )

    assert store.has_running_concurrency_conflict("pending-task", [lock_key]) is True

    claimed = store.try_claim_task(
        "pending-task",
        runner_id="runner-a",
        concurrency_keys=[lock_key],
    )

    assert claimed is False
    assert store.task_status("pending-task") == TaskStatus.PENDING.value


def test_try_claim_task_allows_distinct_concurrency_key():
    store = _SqliteClaimStore()
    store.insert_task(
        "running-task",
        status=TaskStatus.RUNNING.value,
        concurrency_key="concurrency:playbook:other",
    )
    store.insert_task(
        "pending-task",
        status=TaskStatus.PENDING.value,
        concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
    )

    claimed = store.try_claim_task(
        "pending-task",
        runner_id="runner-a",
        concurrency_keys=["concurrency:playbook:ig_analyze_pinned_reference"],
    )

    assert claimed is True
    assert store.task_status("pending-task") == TaskStatus.RUNNING.value


def test_try_claim_task_restores_missing_inputs_from_params():
    store = _SqliteClaimStore()
    store.insert_task(
        "pending-task",
        status=TaskStatus.PENDING.value,
        concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
        params={
            "workspace_id": "ws-1",
            "reference_id": "ref_1",
            "analysis_profile": "visual_anatomy",
        },
        execution_context={
            "runner_skip_reason": "concurrency_locked",
            "resume_after": "2026-05-08T03:05:00+00:00",
        },
    )

    claimed = store.try_claim_task(
        "pending-task",
        runner_id="runner-a",
        concurrency_keys=["concurrency:playbook:ig_analyze_pinned_reference"],
    )

    assert claimed is True
    ctx = store.execution_context("pending-task")
    assert ctx["inputs"]["workspace_id"] == "ws-1"
    assert ctx["inputs"]["reference_id"] == "ref_1"
    assert ctx["inputs"]["analysis_profile"] == "visual_anatomy"
    assert "runner_skip_reason" not in ctx
    assert "resume_after" not in ctx
