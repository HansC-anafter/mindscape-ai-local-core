from datetime import timedelta

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    AdmissionDecision,
)


class _FakePipeline:
    def __init__(self, client):
        self.client = client
        self._pending: list[str] = []
        self._ops: list[tuple[str, str]] = []

    def lpush(self, _queue_name, task_id):
        self._pending.append(task_id)
        self._ops.append(("lpush", task_id))

    def rpush(self, _queue_name, task_id):
        self._pending.append(task_id)
        self._ops.append(("rpush", task_id))

    async def execute(self):
        self.client.enqueued.extend(self._pending)
        self.client.operations.extend(self._ops)


class _FakeRedisClient:
    def __init__(self):
        self.enqueued: list[str] = []
        self.operations: list[tuple[str, str]] = []
        self.pending_members: list[str] = []
        self.processing_members: list[str] = []
        self.delayed_members: list[str] = []

    def pipeline(self):
        return _FakePipeline(self)

    async def lrange(self, _queue_name, _start, _end):
        return list(self.pending_members)

    async def zrange(self, queue_name, _start, _end):
        if "processing" in queue_name:
            return list(self.processing_members)
        if "delayed" in queue_name:
            return list(self.delayed_members)
        return []

    async def mget(self, keys):
        return [None for _key in keys]


class _FakeRedisQueue:
    def __init__(self, pack_id: str):
        self.pack_id = pack_id
        self.q_pending = f"{pack_id}:pending"
        self.q_temp = f"{pack_id}:temp"
        self.q_processing = f"{pack_id}:processing"
        self.q_delayed = f"{pack_id}:delayed"
        self._client = _FakeRedisClient()

    async def _get_client(self):
        return self._client

    async def enqueue_task(self, task_id: str, *, route_identity=None):
        self._client.enqueued.append(task_id)
        self._client.operations.append(("enqueue", task_id))
        return True


class _FakeTasksStore:
    def __init__(self, tasks):
        self._tasks = list(tasks)
        self.updated: list[tuple[str, dict]] = []
        self.release_candidate_calls = 0
        self.concurrency_locked_calls = 0
        self.dependency_hold_calls = 0
        self.resource_wait_calls = 0
        self.workspace_quota_calls = 0
        self.unblocked_cold_calls = 0
        self.ready_workspace_quota_count = 0

    def list_running_playbook_execution_tasks(self, *, workspace_id=None, limit=200):
        return [
            task for task in self._tasks if task.status == TaskStatus.RUNNING
        ][:limit]

    def list_frontier_running_pending_tasks(self, *, workspace_id=None, limit=200):
        return [
            task
            for task in self._tasks
            if task.status == TaskStatus.PENDING
            and getattr(task, "frontier_state", None) == "running"
        ][:limit]

    def list_due_admission_deferred_tasks(self, *, queue_shard=None, limit=200):
        return self._tasks[:limit]

    def list_due_admission_deferred_release_candidates(
        self, *, queue_shard=None, limit=200
    ):
        self.release_candidate_calls += 1
        return self._tasks[:limit]

    def list_due_concurrency_locked_tasks(self, *, queue_shard=None, limit=200):
        self.concurrency_locked_calls += 1
        return self._tasks[:limit]

    def list_due_dependency_hold_tasks(self, *, queue_shard=None, limit=200):
        self.dependency_hold_calls += 1
        return self._tasks[:limit]

    def list_due_resource_wait_tasks(self, *, queue_shard=None, limit=200):
        self.resource_wait_calls += 1
        return self._tasks[:limit]

    def list_due_workspace_quota_tasks(self, *, queue_shard=None, limit=200):
        self.workspace_quota_calls += 1
        return self._tasks[:limit]

    def count_ready_workspace_quota_tasks(
        self, *, workspace_id, queue_shard, selectors
    ):
        return self.ready_workspace_quota_count

    def list_due_unblocked_cold_tasks(self, *, queue_shard=None, limit=200):
        self.unblocked_cold_calls += 1
        return self._tasks[:limit]

    def list_runnable_playbook_execution_tasks(
        self, workspace_id=None, limit=500, queue_shard=None
    ):
        return self._tasks[:limit]

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))


class _FakeAdmissionService:
    def __init__(self, decision: AdmissionDecision):
        self.decision = decision

    def evaluate_on_release(self, _tasks_store, _task):
        return self.decision


class _FakeWorkspaceQuotaDecision:
    def __init__(
        self,
        *,
        allow=True,
        active_count=0,
        max_parallel_task_claims=4,
        reason="workspace_allocation_available",
    ):
        self.allow = allow
        self.reason = reason
        self.active_count = active_count
        self.max_parallel_task_claims = max_parallel_task_claims
        self.allocation = {
            "allocation_id": "alloc-browser",
            "task_family": "ig_browser_capture",
            "metadata": {
                "task_selectors": ["ig_pin_post_detail", "ig_analyze_following"]
            },
        }

    def to_dict(self):
        return {
            "allow": self.allow,
            "reason": self.reason,
            "active_count": self.active_count,
            "max_parallel_task_claims": self.max_parallel_task_claims,
            "allocation": self.allocation,
        }


def _build_deferred_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="ig_analysis",
        created_at=now,
        next_eligible_at=now,
        blocked_reason=ADMISSION_DEFERRED_REASON,
        frontier_state="cold",
        execution_context={
            "auto_triggered": True,
            "admission_policy": {
                "mode": "auto",
                "visibility": "background",
                "producer_kind": "pin_reference",
            },
            "admission": {
                "state": "deferred",
                "reason": "pending_limit",
                "visibility": "background",
                "producer_kind": "pin_reference",
                "queue_shard": "ig_analysis",
            },
        },
    )


def _build_concurrency_locked_task(
    task_id: str = "task-locked",
    concurrency_key: str | None = None,
) -> Task:
    now = _utc_now()
    return Task(
        id=task_id,
        workspace_id="ws-1",
        message_id=f"msg-{task_id}",
        execution_id=f"exec-{task_id}",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        concurrency_key=concurrency_key,
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason="concurrency_locked",
        frontier_state="cold",
        execution_context={
            "playbook_code": "ig_batch_pin_references",
            "runner_skip_reason": "concurrency_locked",
            "runner_skip_lock_key": "concurrency:playbook_input:ig_batch_pin_references:profile-a",
            "runner_skip_conflict_lock_key": "concurrency:playbook_input:ig_batch_pin_references:profile-a",
            "resume_after": now.isoformat(),
            "inputs": {
                "workspace_id": "ws-1",
                "target_handle": "sample",
                "user_data_dir": "profile-a",
            },
        },
    )


def _build_dependency_hold_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-dependency",
        workspace_id="ws-1",
        message_id="msg-dependency",
        execution_id="exec-dependency",
        pack_id="vision_reference_analyze",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="vision_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason="dependency_hold",
        frontier_state="cold",
        execution_context={
            "playbook_code": "vision_reference_analyze",
            "dependency_hold": {"deps": ["mlx"], "checked_at": now.isoformat()},
            "resume_after": now.isoformat(),
        },
    )


def _build_resource_wait_task(
    task_id: str = "task-resource",
    resource_key: str = "mindscape:runner_resources:lease:v1:ig_profile_lock:profile:hash",
    requirements: dict | None = None,
) -> Task:
    now = _utc_now()
    return Task(
        id=task_id,
        workspace_id="ws-1",
        message_id=f"msg-{task_id}",
        execution_id=f"exec-{task_id}",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason="resource_wait",
        frontier_state="cold",
        execution_context={
            "playbook_code": "ig_batch_pin_references",
            "resource_admission": {
                "state": "waiting",
                "reason": "ig_profile_lock_leased",
                "resource_keys": [resource_key],
                "requirements": requirements or {},
            },
            "runner_resource_leases": [{"lease_key": resource_key}],
            "resume_after": now.isoformat(),
        },
    )


def _build_workspace_quota_task(
    task_id: str = "quota_job",
    *,
    blocked_reason: str = "workspace_allocation_quota_exhausted",
) -> Task:
    now = _utc_now()
    return Task(
        id=task_id,
        workspace_id="ws-1",
        message_id=f"msg-{task_id}",
        execution_id=f"exec-{task_id}",
        pack_id="ig_analyze_following",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason=blocked_reason,
        frontier_state="cold",
        execution_context={
            "playbook_code": "ig_analyze_following",
            "workspace_quota_admission": {"reason": blocked_reason},
            "runner_claim_admission": {"runner_profile": "browser_local"},
            "resume_after": now.isoformat(),
        },
    )


def _build_unblocked_cold_task() -> Task:
    now = _utc_now()
    return Task(
        id="task-cold",
        workspace_id="ws-1",
        message_id="msg-cold",
        execution_id="exec-cold",
        pack_id="vision_reference_analyze",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="vision_local",
        created_at=now - timedelta(minutes=5),
        next_eligible_at=now - timedelta(minutes=1),
        blocked_reason=None,
        frontier_state="cold",
        execution_context={"playbook_code": "vision_reference_analyze"},
    )


def _build_stale_queued_running_task_without_owner() -> Task:
    now = _utc_now()
    return Task(
        id="task-orphan-running",
        workspace_id="ws-1",
        message_id="msg-orphan",
        execution_id="exec-orphan",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="browser_local",
        created_at=now - timedelta(hours=2),
        started_at=now - timedelta(hours=2),
        next_eligible_at=now - timedelta(hours=2),
        frontier_state="running",
        execution_context={
            "playbook_code": "ig_batch_pin_references",
            "status": "queued",
            "runner_reaper": {
                "action": "startup_reset",
                "previous_runner_id": "runner-old",
                "new_runner_id": "runner-current",
            },
            "inputs": {
                "workspace_id": "ws-1",
                "target_handle": "sample",
                "user_data_dir": "profile-a",
            },
        },
    )


def _build_running_browser_task(
    *,
    pack_id: str = "browser_profile_scan",
    heartbeat_age_seconds: int = 30,
    current_step_index: int = 0,
    started_age_seconds: int = 3600,
) -> Task:
    now = _utc_now()
    return Task(
        id="task-watchdog",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-watchdog",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        queue_shard="browser_local",
        created_at=now - timedelta(seconds=started_age_seconds),
        started_at=now - timedelta(seconds=started_age_seconds),
        execution_context={
            "runner_id": "runner-1",
            "heartbeat_at": (now - timedelta(seconds=heartbeat_age_seconds)).isoformat(),
            "status": "running",
            "current_step_index": current_step_index,
            "no_progress_watchdog": {
                "enabled": True,
                "artifact_progress_source": "browser_profile_scan_progress",
            },
        },
    )


class _FakeExecution:
    def __init__(self, *, updated_at, created_at=None, phase="queue"):
        self.updated_at = updated_at
        self.created_at = created_at or updated_at
        self.phase = phase


class _FakeExecutionStore:
    def __init__(self, executions):
        self.executions = dict(executions)

    def get_execution(self, execution_id: str):
        return self.executions.get(execution_id)


class _FakeArtifact:
    def __init__(self, *, metadata=None, content=None):
        self.metadata = metadata or {}
        self.content = content or {}


class _FakeArtifactsStore:
    def __init__(self, artifacts):
        self.artifacts = dict(artifacts)

    def get_by_execution_id(self, execution_id: str):
        return self.artifacts.get(execution_id)


class _FakeLiveStateStore:
    def __init__(self, heartbeats):
        self.heartbeats = dict(heartbeats)

    def get_task_heartbeat(self, task_id: str):
        return self.heartbeats.get(task_id)
