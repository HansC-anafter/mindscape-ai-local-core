from contextlib import contextmanager
from datetime import datetime, timezone
import json
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._queries import TasksStoreQueryMixin
from backend.app.services.stores.tasks_store._runner import TasksStoreRunnerMixin


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _SqliteClaimStore(TasksStoreQueryMixin, TasksStoreRunnerMixin):
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
        task_family: str = "ig_browser_capture",
        max_parallel_task_claims: int = 4,
        state: str = "enabled",
        selectors: list[str] | None = None,
    ) -> dict:
        metadata = {"task_selectors": selectors or ["ig_analyze_following"]}
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


def test_update_task_heartbeat_only_reads_abort_state():
    store = _SqliteClaimStore()
    store.insert_task(
        task_id="running-1",
        status=TaskStatus.RUNNING.value,
        pack_id="ig_pin_post_detail",
        execution_context={"status": "running"},
        concurrency_key="profile:nagomi_art",
        blocked_reason="concurrency_locked",
    )

    should_abort = store.update_task_heartbeat("running-1", runner_id="runner-a")

    row = store.fetch_task_row("running-1")
    ctx = store.deserialize_json(row.execution_context)
    assert should_abort is False
    assert row.status == TaskStatus.RUNNING.value
    assert row.runner_id is None
    assert row.heartbeat_at is None
    assert row.blocked_reason == "concurrency_locked"
    assert row.blocked_payload is None
    assert ctx["status"] == "running"
    assert "runner_id" not in ctx
    assert "heartbeat_at" not in ctx
    assert "runner_heartbeat_at" not in ctx


def test_try_claim_task_blocks_pinned_reference_playbook_scope():
    store = _SqliteClaimStore()
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    store.insert_task(
        task_id="running-pinned",
        status=TaskStatus.RUNNING.value,
        pack_id="ig",
        execution_context=_pinned_reference_ctx("ref-a"),
        concurrency_key=lock_key,
    )
    store.insert_task(
        task_id="pending-pinned",
        status=TaskStatus.PENDING.value,
        pack_id="ig",
        execution_context=_pinned_reference_ctx("ref-b"),
        concurrency_key=lock_key,
    )

    claimed = store.try_claim_task("pending-pinned", runner_id="runner-a")

    assert claimed is False
    assert store.fetch_status("pending-pinned") == TaskStatus.PENDING.value


def test_try_claim_task_blocks_workspace_quota_over_parallel_cap():
    store = _SqliteClaimStore()
    allocation = store.insert_allocation(max_parallel_task_claims=4)
    profile_dir = "/app/data/ig-browser-profiles/default"
    for index in range(4):
        store.insert_task(
            task_id=f"running-{index}",
            status=TaskStatus.RUNNING.value,
            pack_id="ig_analyze_following",
            execution_context=_following_ctx(f"{profile_dir}-{index}"),
            concurrency_key=f"ig_profile:{profile_dir}-{index}",
        )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(f"{profile_dir}-pending"),
        concurrency_key=f"ig_profile:{profile_dir}-pending",
    )

    claimed = store.try_claim_task(
        "pending-1",
        runner_id="runner-a",
        workspace_quota_decision=SimpleNamespace(
            to_dict=lambda: {"allow": True, "allocation": allocation}
        ),
    )

    assert claimed is False
    assert store.fetch_status("pending-1") == TaskStatus.PENDING.value


def test_try_claim_task_allows_workspace_quota_at_available_slot():
    store = _SqliteClaimStore()
    allocation = store.insert_allocation(max_parallel_task_claims=4)
    profile_dir = "/app/data/ig-browser-profiles/default"
    for index in range(3):
        store.insert_task(
            task_id=f"running-{index}",
            status=TaskStatus.RUNNING.value,
            pack_id="ig_analyze_following",
            execution_context=_following_ctx(f"{profile_dir}-{index}"),
            concurrency_key=f"ig_profile:{profile_dir}-{index}",
        )
    store.insert_task(
        task_id="pending-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context=_following_ctx(f"{profile_dir}-pending"),
        concurrency_key=f"ig_profile:{profile_dir}-pending",
    )

    claimed = store.try_claim_task(
        "pending-1",
        runner_id="runner-a",
        workspace_quota_decision=SimpleNamespace(
            to_dict=lambda: {"allow": True, "allocation": allocation}
        ),
    )

    assert claimed is True
    assert store.fetch_status("pending-1") == TaskStatus.RUNNING.value


def test_try_release_workspace_quota_task_moves_cold_task_to_ready():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=4,
        selectors=["ig_analyze_following", "ig_pin_post_detail"],
    )
    store.insert_task(
        task_id="quota-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context={
            "playbook_code": "ig_analyze_following",
            "workspace_quota_admission": {"reason": "quota"},
        },
        concurrency_key=None,
        blocked_reason="workspace_allocation_quota_exhausted",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "quota-cold-1",
        workspace_id="ws-1",
        queue_shard="browser_local",
        selectors=["ig_analyze_following", "ig_pin_post_detail"],
        task_selector="ig_analyze_following",
        allocation_key="alloc-browser",
        max_parallel_task_claims=4,
        execution_context={"playbook_code": "ig_analyze_following"},
    )

    row = store.fetch_task_row("quota-cold-1")
    assert released is True
    assert store.fetch_frontier("quota-cold-1") == "ready"
    assert row.blocked_reason is None
    assert row.blocked_payload is None
    assert store.deserialize_json(row.execution_context) == {
        "playbook_code": "ig_analyze_following"
    }


def test_try_release_workspace_quota_task_blocks_same_selector_when_reserved_full():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=4,
        selectors=["ig_analyze_following", "ig_pin_post_detail"],
    )
    for index in range(4):
        store.insert_task(
            task_id=f"ready-following-{index}",
            status=TaskStatus.PENDING.value,
            pack_id="ig_analyze_following",
            execution_context={"playbook_code": "ig_analyze_following"},
            concurrency_key=None,
            frontier_state="ready",
        )
    store.insert_task(
        task_id="quota-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context={"playbook_code": "ig_analyze_following"},
        concurrency_key=None,
        blocked_reason="workspace_allocation_quota_exhausted",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "quota-cold-1",
        workspace_id="ws-1",
        queue_shard="browser_local",
        selectors=["ig_analyze_following", "ig_pin_post_detail"],
        task_selector="ig_analyze_following",
        allocation_key="alloc-browser",
        max_parallel_task_claims=4,
        execution_context={"playbook_code": "ig_analyze_following"},
    )

    assert released is False
    assert store.fetch_frontier("quota-cold-1") == "cold"


def test_try_release_workspace_quota_task_allows_one_missing_selector_candidate():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=4,
        selectors=["ig_analyze_following", "ig_pin_post_detail"],
    )
    for index in range(4):
        store.insert_task(
            task_id=f"ready-detail-{index}",
            status=TaskStatus.PENDING.value,
            pack_id="ig_pin_post_detail",
            execution_context={"playbook_code": "ig_pin_post_detail"},
            concurrency_key=None,
            frontier_state="ready",
        )
    store.insert_task(
        task_id="quota-cold-following",
        status=TaskStatus.PENDING.value,
        pack_id="ig_analyze_following",
        execution_context={"playbook_code": "ig_analyze_following"},
        concurrency_key=None,
        blocked_reason="workspace_allocation_quota_exhausted",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "quota-cold-following",
        workspace_id="ws-1",
        queue_shard="browser_local",
        selectors=["ig_analyze_following", "ig_pin_post_detail"],
        task_selector="ig_analyze_following",
        allocation_key="alloc-browser",
        max_parallel_task_claims=4,
        execution_context={"playbook_code": "ig_analyze_following"},
    )

    assert released is True
    assert store.fetch_frontier("quota-cold-following") == "ready"


def test_try_release_workspace_quota_task_moves_allocation_required_cold_task_to_ready():
    store = _SqliteClaimStore()
    store.insert_allocation(
        max_parallel_task_claims=1,
        queue_shard="decision_synthesis",
        task_family="decision_assets_synthesize",
        selectors=["decision_assets_synthesize"],
    )
    store.insert_task(
        task_id="decision-cold-1",
        status=TaskStatus.PENDING.value,
        pack_id="decision_assets_synthesize",
        execution_context={"playbook_code": "decision_assets_synthesize"},
        concurrency_key=None,
        queue_shard="decision_synthesis",
        task_type="playbook_execution",
        blocked_reason="workspace_allocation_required",
        frontier_state="cold",
    )

    released = store.try_release_workspace_quota_task(
        "decision-cold-1",
        workspace_id="ws-1",
        queue_shard="decision_synthesis",
        selectors=["decision_assets_synthesize"],
        task_selector="decision_assets_synthesize",
        allocation_key="alloc-decision",
        max_parallel_task_claims=1,
        execution_context={"playbook_code": "decision_assets_synthesize"},
    )

    row = store.fetch_task_row("decision-cold-1")
    assert released is True
    assert store.fetch_frontier("decision-cold-1") == "ready"
    assert row.blocked_reason is None


def test_list_due_workspace_quota_tasks_includes_allocation_required_and_disabled():
    store = _SqliteClaimStore()
    for task_id, blocked_reason in (
        ("decision-required", "workspace_allocation_required"),
        ("decision-disabled", "workspace_allocation_disabled"),
        ("decision-quota", "workspace_allocation_quota_exhausted"),
    ):
        store.insert_task(
            task_id=task_id,
            status=TaskStatus.PENDING.value,
            pack_id="decision_assets_synthesize",
            execution_context={"playbook_code": "decision_assets_synthesize"},
            concurrency_key=None,
            queue_shard="decision_synthesis",
            task_type="playbook_execution",
            blocked_reason=blocked_reason,
            frontier_state="cold",
            created_at=_utc_now(),
            next_eligible_at=_utc_now(),
        )

    tasks = store.list_due_workspace_quota_tasks(
        queue_shard="decision_synthesis",
        limit=10,
    )

    assert {task.id for task in tasks} == {
        "decision-required",
        "decision-disabled",
        "decision-quota",
    }
    assert {task.blocked_reason for task in tasks} == {
        "workspace_allocation_required",
        "workspace_allocation_disabled",
        "workspace_allocation_quota_exhausted",
    }
