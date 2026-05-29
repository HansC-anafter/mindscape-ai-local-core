from contextlib import contextmanager
from datetime import datetime, timezone
import json

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._runner import TasksStoreRunnerMixin


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
                        pack_id TEXT NOT NULL,
                        concurrency_key TEXT,
                        started_at TIMESTAMP,
                        runner_id TEXT,
                        heartbeat_at TIMESTAMP,
                        blocked_reason TEXT,
                        blocked_payload TEXT,
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

    @contextmanager
    def transaction(self):
        with self.get_connection() as conn:
            yield conn

    def serialize_json(self, data):
        return json.dumps(data)

    def deserialize_json(self, data, default=None):
        if data is None:
            return {} if default is None else default
        if isinstance(data, (dict, list)):
            return data
        if isinstance(data, str):
            return json.loads(data)
        return {} if default is None else default

    def insert_task(
        self,
        *,
        task_id: str,
        status: str,
        pack_id: str,
        execution_context: dict,
        concurrency_key: str | None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id, status, params, execution_context, pack_id, concurrency_key,
                        started_at, blocked_reason, blocked_payload, frontier_state, frontier_enqueued_at
                    ) VALUES (
                        :id, :status, :params, :execution_context, :pack_id, :concurrency_key,
                        NULL, NULL, NULL, :frontier_state, NULL
                    )
                    """
                ),
                {
                    "id": task_id,
                    "status": status,
                    "params": self.serialize_json({}),
                    "execution_context": self.serialize_json(execution_context),
                    "pack_id": pack_id,
                    "concurrency_key": concurrency_key,
                    "frontier_state": (
                        "running" if status == TaskStatus.RUNNING.value else "ready"
                    ),
                },
            )

    def fetch_status(self, task_id: str) -> str:
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT status FROM tasks WHERE id = :task_id"),
                {"task_id": task_id},
            ).fetchone()
        return str(row[0])


def _following_ctx(user_data_dir: str) -> dict:
    return {
        "playbook_code": "ig_analyze_following",
        "inputs": {
            "user_data_dir": user_data_dir,
            "target_username": "demo_target",
        },
    }


def test_try_claim_task_blocks_same_profile_running_conflict():
    store = _SqliteClaimStore()
    profile_dir = "/app/data/ig-browser-profiles/default"
    lock_key = f"ig_profile:{profile_dir}"
    store.insert_task(
        task_id="running-1",
        status=TaskStatus.RUNNING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(profile_dir),
        concurrency_key=lock_key,
    )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(profile_dir),
        concurrency_key=lock_key,
    )

    claimed = store.try_claim_task("pending-1", runner_id="runner-a")

    assert claimed is False
    assert store.fetch_status("pending-1") == TaskStatus.PENDING.value


def test_try_claim_task_allows_distinct_profile():
    store = _SqliteClaimStore()
    default_dir = "/app/data/ig-browser-profiles/default"
    walto_dir = "/app/data/ig-browser-profiles/walto_lab"
    store.insert_task(
        task_id="running-1",
        status=TaskStatus.RUNNING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(default_dir),
        concurrency_key=f"ig_profile:{default_dir}",
    )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(walto_dir),
        concurrency_key=f"ig_profile:{walto_dir}",
    )

    claimed = store.try_claim_task("pending-1", runner_id="runner-a")

    assert claimed is True
    assert store.fetch_status("pending-1") == TaskStatus.RUNNING.value
