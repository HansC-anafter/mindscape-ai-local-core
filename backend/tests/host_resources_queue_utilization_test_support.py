from backend.app.services.host_resources.route_identity_projection import (
    serialize_route_identity_projection,
)


class FakeRedisClient:
    def __init__(self, pending_ids):
        self.pending_ids = list(pending_ids)
        self.projections = {}
        self.llen_values = {}
        self.zcard_values = {}
        self.lrange_calls = []
        self.lease_available = True
        self.set_calls = []

    async def lrange(self, key, start, end):
        self.lrange_calls.append((key, start, end))
        return self.pending_ids[start : end + 1]

    async def mget(self, keys):
        return [self.projections.get(key) for key in keys]

    async def llen(self, key):
        return self.llen_values.get(key, 0)

    async def zcard(self, key):
        return self.zcard_values.get(key, 0)

    async def set(self, key, value, nx=False, ex=None):
        self.set_calls.append((key, value, nx, ex))
        if not self.lease_available:
            return False
        self.lease_available = False
        return True


class FakeQueue:
    def __init__(self, pack_id, pending_ids):
        self.pack_id = pack_id
        self.q_pending = f"pending:{pack_id}"
        self.q_processing = f"processing:{pack_id}"
        self.q_delayed = f"delayed:{pack_id}"
        self.q_deadletter = f"deadletter:{pack_id}"
        self.client = FakeRedisClient(pending_ids)
        self.client.llen_values[self.q_pending] = len(pending_ids)
        self.client.llen_values[self.q_deadletter] = 0
        self.client.zcard_values[self.q_processing] = 2
        self.client.zcard_values[self.q_delayed] = 1

    async def _get_client(self):
        return self.client


class FakeSnapshotStore:
    def __init__(self):
        self.saved = []
        self.deleted = False

    def save_snapshot_batch(self, snapshot):
        self.saved.append(snapshot)
        return len(snapshot["queue_depths"])

    def delete_old_snapshots(self):
        self.deleted = True
        return 0


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        return FakeResult(self.rows)


class FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


def projection(task_id, pack_id, concurrency_key):
    return serialize_route_identity_projection(
        task_id,
        {
            "task_id": task_id,
            "pack_id": pack_id,
            "playbook_code": pack_id,
            "queue_shard": "browser_local",
            "concurrency_key": concurrency_key,
            "route_identity": {
                "lane_id": "runner:browser_local",
                "resource_groups": ["browser_local"],
                "priority_class": "default",
                "pack_id": pack_id,
                "playbook_code": pack_id,
            },
        },
    )
