from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._base import TasksStoreCrudMixin


class _Result:
    rowcount = 1


class _Connection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((str(query), dict(params)))
        return _Result()


def test_pending_task_projects_playbook_execution_as_queued():
    store = object.__new__(TasksStoreCrudMixin)
    conn = _Connection()

    store._sync_playbook_execution_status(
        conn,
        "execution-1",
        TaskStatus.PENDING,
        {"status": "queued"},
    )

    assert len(conn.calls) == 1
    query, params = conn.calls[0]
    assert "UPDATE playbook_executions" in query
    assert "status NOT IN ('done', 'failed')" in query
    assert params["id"] == "execution-1"
    assert params["status"] == "queued"
