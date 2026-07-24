from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.runner_topology.profile_registry import RunnerProfile

BATCH_PLAYBOOK = "browser_batch_collect"
DETAIL_PLAYBOOK = "browser_detail_collect"
FOLLOWING_PLAYBOOK = "browser_following_collect"
VISION_PLAYBOOK = "vision_reference_analyze"
MANAGED_BATCH_PLAYBOOKS = {BATCH_PLAYBOOK, DETAIL_PLAYBOOK}


class FakeFairClient:
    def __init__(self, ids):
        self.ids = ids
        self.projections = {}
        self.values = {}
        self.setex_calls = []
        self.incrby_calls = []
        self.expire_calls = []

    async def llen(self, queue_name):
        return len(self.ids)

    async def lrange(self, queue_name, start, end):
        return self.ids[start : end + 1]

    async def mget(self, keys):
        return [self.projections.get(key) for key in keys]

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl_seconds, value):
        self.values[key] = value
        self.setex_calls.append((key, ttl_seconds, value))
        return True

    async def incrby(self, key, amount):
        next_value = int(self.values.get(key) or 0) + int(amount)
        self.values[key] = next_value
        self.incrby_calls.append((key, amount))
        return next_value

    async def expire(self, key, ttl_seconds):
        self.expire_calls.append((key, ttl_seconds))
        return True


class FakeFairQueue:
    def __init__(self, ids, pack_id: str = "browser_local"):
        self.pack_id = pack_id
        self.q_pending = f"pending:{pack_id}"
        self.client = FakeFairClient(ids)
        self.promoted: list[str] = []

    async def _get_client(self):
        return self.client

    async def promote_pending_task_by_id(
        self,
        task_id: str,
        visibility_timeout_sec: int = 180,
    ):
        self.promoted.append(task_id)
        return task_id


class FakeCandidateTasksStore:
    def __init__(self, projections, running_counts):
        self.projections = projections
        self.running_counts = running_counts
        self.requested_ids: list[str] = []
        self.requested_queue_shard = None

    def list_runner_candidate_projections_by_ids(self, task_ids, queue_shard):
        self.requested_ids = list(task_ids)
        self.requested_queue_shard = queue_shard
        return [
            self.projections[task_id]
            for task_id in task_ids
            if task_id in self.projections
        ]

    def count_running_browser_lanes(self, queue_shard):
        self.requested_queue_shard = queue_shard
        return dict(self.running_counts)


def pending_browser_task(task_id: str, pack_id: str) -> Task:
    now = _utc_now()
    queue_shard = (
        "default_local_browser"
        if pack_id in MANAGED_BATCH_PLAYBOOKS
        else "browser_local"
    )
    return Task(
        id=task_id,
        workspace_id="ws-1",
        message_id=f"msg-{task_id}",
        execution_id=f"exec-{task_id}",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard=queue_shard,
        execution_context={"queue_shard": queue_shard},
        created_at=now,
    )


def projection(
    task_id: str,
    pack_id: str,
    *,
    lane_id: str = "runner:default_local_browser",
):
    queue_shard = (
        "default_local_browser"
        if pack_id in MANAGED_BATCH_PLAYBOOKS
        else "browser_local"
    )
    return {
        "task_id": task_id,
        "pack_id": pack_id,
        "playbook_code": pack_id,
        "task_type": "playbook_execution",
        "workspace_id": "ws-1",
        "queue_shard": queue_shard,
        "route_identity": {
            "lane_id": lane_id,
            "resource_groups": [lane_id],
            "priority_class": "default",
            "pack_id": pack_id,
            "playbook_code": pack_id,
        },
    }


def candidate_projection(task_id: str, pack_id: str):
    queue_shard = (
        "default_local_browser"
        if pack_id in MANAGED_BATCH_PLAYBOOKS
        else "browser_local"
    )
    return {
        "task_id": task_id,
        "id": task_id,
        "pack_id": pack_id,
        "playbook_code": pack_id,
        "task_type": "playbook_execution",
        "status": "pending",
        "frontier_state": "ready",
        "queue_shard": queue_shard,
        "execution_context": {
            "playbook_code": pack_id,
            "queue_shard": queue_shard,
        },
    }


def browser_profile() -> RunnerProfile:
    return RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
        max_inflight=2,
    )


def default_profile() -> RunnerProfile:
    return RunnerProfile(
        profile_code="default_local_browser",
        display_name="Default",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("default_local_browser",),
        max_inflight=2,
    )


def compute_profile() -> RunnerProfile:
    return RunnerProfile(
        profile_code="vision_local",
        display_name="Vision",
        dispatch_mode="docker_local",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("vision_local",),
        max_inflight=2,
    )
