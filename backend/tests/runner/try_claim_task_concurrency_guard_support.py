from contextlib import contextmanager
from datetime import datetime, timezone
import json

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._queries import TasksStoreQueryMixin
from backend.app.services.stores.tasks_store._runner import TasksStoreRunnerMixin
from backend.app.services.stores.tasks_store._crud_update import TasksStoreUpdateMixin


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _SqliteClaimStore(
    TasksStoreQueryMixin,
    TasksStoreRunnerMixin,
    TasksStoreUpdateMixin,
):
    def __init__(self) -> None:
        self.projection_refreshes: list[str] = []
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
                        workspace_id TEXT,
                        message_id TEXT,
                        execution_id TEXT,
                        status TEXT NOT NULL,
                        params TEXT,
                        execution_context TEXT,
                        pack_id TEXT NOT NULL,
                        task_type TEXT,
                        queue_shard TEXT,
                        concurrency_key TEXT,
                        created_at TIMESTAMP,
                        next_eligible_at TIMESTAMP,
                        started_at TIMESTAMP,
                        completed_at TIMESTAMP,
                        runner_id TEXT,
                        heartbeat_at TIMESTAMP,
                        error TEXT,
                        blocked_reason TEXT,
                        blocked_payload TEXT,
                        frontier_state TEXT,
                        frontier_enqueued_at TIMESTAMP
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE host_resource_workspace_allocations (
                        allocation_id TEXT PRIMARY KEY,
                        workspace_id TEXT NOT NULL,
                        queue_shard TEXT NOT NULL,
                        task_family TEXT NOT NULL,
                        state TEXT NOT NULL,
                        max_parallel_task_claims INTEGER NOT NULL,
                        metadata TEXT
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

    def _coerce_datetime(self, value):
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    def _refresh_task_projection(self, _conn, task_id: str, **_kwargs) -> None:
        self.projection_refreshes.append(task_id)

    def insert_task(
        self,
        *,
        task_id: str,
        status: str,
        pack_id: str,
        execution_context: dict,
        concurrency_key: str | None,
        workspace_id: str = "ws-1",
        queue_shard: str = "browser_local",
        task_type: str | None = None,
        blocked_reason: str | None = None,
        frontier_state: str | None = None,
        next_eligible_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> None:
        created_at = created_at or _utc_now()
        next_eligible_at = next_eligible_at or created_at
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO tasks (
                        id, workspace_id, message_id, execution_id, status, params, execution_context,
                        pack_id, task_type, queue_shard, concurrency_key,
                        created_at, next_eligible_at, started_at, completed_at,
                        blocked_reason, blocked_payload, frontier_state, frontier_enqueued_at
                    ) VALUES (
                        :id, :workspace_id, :message_id, :execution_id, :status, :params, :execution_context,
                        :pack_id, :task_type, :queue_shard, :concurrency_key,
                        :created_at, :next_eligible_at, NULL, NULL,
                        :blocked_reason, NULL, :frontier_state, NULL
                    )
                    """
                ),
                {
                    "id": task_id,
                    "workspace_id": workspace_id,
                    "message_id": f"msg-{task_id}",
                    "execution_id": f"exec-{task_id}",
                    "status": status,
                    "params": self.serialize_json({}),
                    "execution_context": self.serialize_json(execution_context),
                    "pack_id": pack_id,
                    "task_type": task_type or pack_id,
                    "queue_shard": queue_shard,
                    "concurrency_key": concurrency_key,
                    "created_at": created_at,
                    "next_eligible_at": next_eligible_at,
                    "blocked_reason": blocked_reason,
                    "frontier_state": (
                        frontier_state
                        or (
                            "running"
                            if status == TaskStatus.RUNNING.value
                            else "ready"
                        )
                    ),
                },
            )

    def insert_allocation(
        self,
        *,
        allocation_id: str = "alloc-browser",
        workspace_id: str = "ws-1",
        queue_shard: str = "browser_local",
        task_family: str = "browser_batch",
        max_parallel_task_claims: int = 4,
        state: str = "enabled",
        selectors: list[str] | None = None,
    ) -> dict:
        metadata = {
            "task_selectors": selectors
            or ["ig_batch_pin_references", "ig_pin_post_detail"]
        }
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO host_resource_workspace_allocations (
                        allocation_id, workspace_id, queue_shard, task_family,
                        state, max_parallel_task_claims, metadata
                    ) VALUES (
                        :allocation_id, :workspace_id, :queue_shard, :task_family,
                        :state, :max_parallel_task_claims, :metadata
                    )
                    """
                ),
                {
                    "allocation_id": allocation_id,
                    "workspace_id": workspace_id,
                    "queue_shard": queue_shard,
                    "task_family": task_family,
                    "state": state,
                    "max_parallel_task_claims": max_parallel_task_claims,
                    "metadata": self.serialize_json(metadata),
                },
            )
        return {
            "allocation_id": allocation_id,
            "workspace_id": workspace_id,
            "queue_shard": queue_shard,
            "task_family": task_family,
            "state": state,
            "max_parallel_task_claims": max_parallel_task_claims,
            "metadata": metadata,
        }

    def fetch_task_row(self, task_id: str):
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, runner_id, heartbeat_at, blocked_reason,
                           blocked_payload, execution_context
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
        return row

    def fetch_status(self, task_id: str) -> str:
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT status FROM tasks WHERE id = :task_id"),
                {"task_id": task_id},
            ).fetchone()
        return str(row[0])

    def fetch_frontier(self, task_id: str) -> str:
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT frontier_state FROM tasks WHERE id = :task_id"),
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


def _pinned_reference_ctx(reference_id: str) -> dict:
    return {
        "playbook_code": "ig_analyze_pinned_reference",
        "inputs": {
            "reference_id": reference_id,
        },
        "concurrency": {
            "lock_scope": "playbook",
            "max_parallel": 1,
        },
    }
