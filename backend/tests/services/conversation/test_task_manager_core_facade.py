import asyncio
from datetime import timedelta

from backend.app.models.workspace import SideEffectLevel, Task, TaskStatus
from backend.app.services.conversation.task_manager import TaskManager
from backend.app.services.conversation.task_manager_core import artifacts as artifact_facade
from backend.app.services.conversation.task_manager_core import timeouts as timeout_helpers
from backend.app.services.execution_core.clock import utc_now


class FakeI18n:
    def t(self, namespace, key, default=None, **kwargs):
        assert namespace == "conversation_orchestrator"
        if default is not None:
            return default
        return f"{key}:{kwargs}"


class FakePlanBuilder:
    def determine_side_effect_level(self, playbook_code):
        return SideEffectLevel.READONLY


class FakeTasksStore:
    def __init__(self, tasks=None):
        self.tasks = {task.id: task for task in (tasks or [])}
        self.status_updates = []
        self.updates = []

    def update_task_status(self, task_id, status, result=None, error=None, completed_at=None):
        self.status_updates.append(
            {
                "task_id": task_id,
                "status": status,
                "result": result,
                "error": error,
                "completed_at": completed_at,
            }
        )
        task = self.tasks.get(task_id)
        if task:
            task.status = status
            task.result = result if result is not None else task.result
            task.error = error
            task.completed_at = completed_at

    def update_task(self, task_id, **updates):
        self.updates.append((task_id, updates))
        task = self.tasks.get(task_id)
        if task:
            for key, value in updates.items():
                setattr(task, key, value)

    def list_tasks_by_workspace(self, workspace_id, status, limit):
        return [task for task in self.tasks.values() if task.status == status][:limit]


class FakeTimelineItemsStore:
    def __init__(self):
        self.created = []

    def create_timeline_item(self, timeline_item):
        self.created.append(timeline_item)


class RunnerWithoutResultMethods:
    pass


def make_task(**overrides):
    base = {
        "id": "task-1",
        "workspace_id": "ws-1",
        "message_id": "msg-1",
        "pack_id": "planning",
        "task_type": "plan",
        "status": TaskStatus.RUNNING,
        "params": {},
    }
    base.update(overrides)
    return Task(**base)


def make_manager(tasks_store, timeline_items_store, playbook_runner=None):
    manager = TaskManager(
        tasks_store=tasks_store,
        timeline_items_store=timeline_items_store,
        plan_builder=FakePlanBuilder(),
        playbook_runner=playbook_runner or RunnerWithoutResultMethods(),
    )
    manager.i18n = FakeI18n()
    return manager


def test_artifact_facade_preserves_public_exports():
    assert hasattr(artifact_facade, "attach_artifact_to_timeline_item")
    assert hasattr(artifact_facade, "resolve_task_intent_id")
    assert hasattr(artifact_facade, "update_artifact_latest_markers")


def test_task_manager_create_timeline_item_preserves_success_lifecycle():
    task = make_task()
    tasks_store = FakeTasksStore([task])
    timeline_items_store = FakeTimelineItemsStore()
    manager = make_manager(tasks_store, timeline_items_store)
    graph_calls = []

    async def graph_stub(**kwargs):
        graph_calls.append(kwargs)

    manager._create_graph_node_for_task = graph_stub

    timeline_item = asyncio.run(
        manager.create_timeline_item_from_task(
            task=task,
            execution_result={"title": "Plan Ready", "summary": "A structured plan"},
            playbook_code="planning",
        )
    )

    assert timeline_item is not None
    assert timeline_items_store.created == [timeline_item]
    assert tasks_store.status_updates[-1]["status"] == TaskStatus.SUCCEEDED
    assert graph_calls and graph_calls[0]["task"] == task
    assert any(
        task_id == task.id and "notification_sent_at" in updates
        for task_id, updates in tasks_store.updates
    )


def test_task_manager_status_polling_preserves_missing_result_failure():
    task = make_task(execution_id="exec-1")
    tasks_store = FakeTasksStore([task])
    timeline_items_store = FakeTimelineItemsStore()
    manager = make_manager(tasks_store, timeline_items_store)

    asyncio.run(
        manager.check_and_update_task_status(
            task=task,
            execution_id="exec-1",
            playbook_code="planning",
        )
    )

    assert tasks_store.status_updates[-1]["status"] == TaskStatus.FAILED
    assert tasks_store.status_updates[-1]["error"] == (
        "Execution completed but no result available"
    )
    assert len(timeline_items_store.created) == 1
    assert timeline_items_store.created[0].task_id == task.id


def test_task_manager_timeout_preserves_failure_and_diagnostic(monkeypatch):
    task = make_task(
        id="task-timeout",
        execution_id="exec-timeout",
        started_at=utc_now() - timedelta(minutes=10),
        execution_context={},
    )
    tasks_store = FakeTasksStore([task])
    timeline_items_store = FakeTimelineItemsStore()
    manager = make_manager(tasks_store, timeline_items_store)

    def fake_collect_timeout_diagnostics(**kwargs):
        return {
            "pack_id": task.pack_id,
            "execution_id": kwargs["execution_id"],
            "diagnosis": "test diagnosis",
        }

    monkeypatch.setattr(
        timeout_helpers,
        "collect_timeout_diagnostics",
        fake_collect_timeout_diagnostics,
    )

    timed_out = manager.check_and_timeout_tasks(timeout_minutes=5)

    assert timed_out == [task.id]
    assert tasks_store.status_updates[-1]["status"] == TaskStatus.FAILED
    assert tasks_store.updates[-1][0] == task.id
    assert tasks_store.updates[-1][1]["execution_context"]["failure_type"] == "timeout"
    assert (
        tasks_store.updates[-1][1]["execution_context"]["timeout_diagnostic"][
            "diagnosis"
        ]
        == "test diagnosis"
    )
    assert len(timeline_items_store.created) == 1
    assert timeline_items_store.created[0].task_id == task.id
