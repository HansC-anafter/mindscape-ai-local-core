from contextlib import contextmanager
from datetime import datetime, timezone

from app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store._base import TasksStoreCrudMixin


class _Connection:
    def execute(self, _query, _params):
        return None


class _Store(TasksStoreCrudMixin):
    def __init__(self):
        self.events = []

    @contextmanager
    def transaction(self):
        self.events.append("transaction_started")
        yield _Connection()
        self.events.append("transaction_committed")

    def serialize_json(self, data):
        return data

    def _sync_playbook_execution_status(
        self,
        _conn,
        execution_id,
        status,
        _execution_context=None,
    ):
        self.events.append(("projection_synced", execution_id, status.value))

    def _record_run_control_from_task(self, _conn, _task):
        return None

    def _record_task_control_event(self, _conn, **_kwargs):
        return None

    def _refresh_task_projection(self, _conn, _task_id):
        return None

    def _enqueue_runner_task_after_commit(self, _task):
        self.events.append("post_commit_enqueue")


def _task(task_type="playbook_execution"):
    return Task(
        id="queue_task_1",
        workspace_id="workspace-1",
        message_id="message-1",
        execution_id="execution-1",
        pack_id="ig_analyze_following",
        task_type=task_type,
        status=TaskStatus.PENDING,
        params={},
        result={},
        execution_context={"status": "queued"},
        storyline_tags=[],
        created_at=datetime.now(timezone.utc),
    )


def test_create_task_syncs_playbook_projection_before_commit():
    store = _Store()

    store.create_task(_task())

    assert store.events == [
        "transaction_started",
        ("projection_synced", "execution-1", "pending"),
        "transaction_committed",
        "post_commit_enqueue",
    ]


def test_create_task_skips_playbook_projection_for_non_runner_task():
    store = _Store()

    store.create_task(_task(task_type="agent_dispatch"))

    assert not any(
        isinstance(event, tuple) and event[0] == "projection_synced"
        for event in store.events
    )
