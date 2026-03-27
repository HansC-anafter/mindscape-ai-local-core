from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.queue_position_cache import QueuePositionCache


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
                        frontier_state TEXT
                    )
                    """
                )
            )

    @contextmanager
    def get_connection(self):
        with self._engine.begin() as conn:
            yield conn

    def insert_row(self, **row) -> None:
        with self._engine.begin() as conn:
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
                        frontier_state
                    ) VALUES (
                        :id,
                        :task_type,
                        :status,
                        :blocked_reason,
                        :queue_shard,
                        :created_at,
                        :next_eligible_at,
                        :frontier_state
                    )
                    """
                ),
                row,
            )


def test_queue_position_cache_merges_legacy_alias_totals_into_canonical_partition():
    store = _SqliteTasksStore()
    cache = QueuePositionCache()
    now = _utc_now()

    store.insert_row(
        id="legacy-1",
        task_type="playbook_execution",
        status="pending",
        blocked_reason=None,
        queue_shard="ig_browser",
        created_at=now - timedelta(minutes=4),
        next_eligible_at=now - timedelta(minutes=4),
        frontier_state="ready",
    )
    store.insert_row(
        id="canonical-1",
        task_type="playbook_execution",
        status="pending",
        blocked_reason=None,
        queue_shard="browser_local",
        created_at=now - timedelta(minutes=3),
        next_eligible_at=now - timedelta(minutes=3),
        frontier_state="ready",
    )

    cache.refresh_if_stale(store, max_age=0.0)

    assert cache.get_total("browser_local") == 2
    assert cache.get_total("ig_browser") == 2


def test_queue_position_cache_estimates_position_against_legacy_alias_rows():
    store = _SqliteTasksStore()
    cache = QueuePositionCache()
    now = _utc_now()

    store.insert_row(
        id="legacy-ahead",
        task_type="playbook_execution",
        status="pending",
        blocked_reason=None,
        queue_shard="ig_browser",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=5),
        frontier_state="ready",
    )

    task = Task(
        id="canonical-task",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        created_at=now - timedelta(minutes=1),
        next_eligible_at=now - timedelta(minutes=1),
        frontier_state="ready",
    )

    cache.refresh_if_stale(store, max_age=0.0)

    assert cache.get_position(store, task) == 2
