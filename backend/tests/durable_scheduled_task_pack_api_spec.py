from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from backend.app.services.knowledge_projection.retrievable.canonical_json import (
    canonical_sha256,
)
from backend.app.services.workflow.scheduled_task_pack_api import (
    DurableScheduledTaskCommand,
    DurableScheduledTaskFacade,
    InstalledToolSelector,
)


class _Registry:
    def get_tool(self, name):
        return {"name": name} if name == "frontier_research.run_cycle" else None


class _Timer:
    def __init__(self) -> None:
        self.calls = []

    def record_timer(self, conn, **kwargs):
        self.calls.append((conn, kwargs))
        return {"sequence": 8}


class _Tasks:
    def __init__(self) -> None:
        self.rows = {}
        self.conn = object()
        self.finalized = []

    def prepare_task_for_create(self, task):
        assert task.next_eligible_at > datetime.now(timezone.utc)
        task.frontier_state = "cold"
        return task

    @contextmanager
    def transaction(self):
        yield self.conn

    def create_task_with_conn(
        self,
        conn,
        task,
        *,
        already_prepared,
        idempotent,
    ):
        assert conn is self.conn
        assert already_prepared is True
        assert idempotent is True
        existing = self.rows.get(task.id)
        if existing is not None:
            return existing, False
        self.rows[task.id] = task
        return task, True

    def finalize_task_create_after_commit(self, task, *, created):
        self.finalized.append((task.id, created))
        return task


def _command():
    payload = {"trunk_id": "bird-evolution", "cycle_revision": 7}
    return DurableScheduledTaskCommand(
        workflow_id="frontier-cycle:bird-evolution",
        expected_sequence=7,
        timer_id="discovery-next-7",
        deadline="2030-07-30T00:00:00Z",
        workspace_id="ws_demo",
        selector=InstalledToolSelector(
            capability_code="frontier_research",
            tool_code="run_cycle",
        ),
        payload=payload,
        payload_digest=canonical_sha256(payload),
        actor={
            "actor_type": "service",
            "actor_id": "frontier-research",
        },
        idempotency_key="frontier-cycle:bird-evolution:timer:7",
    )


def test_schedule_next_uses_one_transaction_and_is_idempotent():
    timer = _Timer()
    tasks = _Tasks()
    facade = DurableScheduledTaskFacade(
        durable_timer=timer,
        tasks_store=tasks,
        tool_registry=_Registry(),
    )

    first = facade.schedule_next(_command())
    second = facade.schedule_next(_command())

    assert first.task_created is True
    assert second.task_created is False
    assert first.task_id == second.task_id
    assert first.timer_sequence == 8
    assert timer.calls[0][0] is tasks.conn
    assert timer.calls[0][1]["timer"]["selector"] == (
        "frontier_research.run_cycle"
    )
    assert len(tasks.rows) == 1
    assert tasks.finalized == [
        (first.task_id, True),
        (first.task_id, False),
    ]


def test_schedule_next_rejects_uninstalled_tool_before_transaction():
    facade = DurableScheduledTaskFacade(
        durable_timer=_Timer(),
        tasks_store=_Tasks(),
        tool_registry=type(
            "_MissingRegistry",
            (),
            {"get_tool": lambda self, name: None},
        )(),
    )
    try:
        facade.schedule_next(_command())
    except ValueError as exc:
        assert str(exc) == "durable_scheduled_task_installed_tool_required"
    else:
        raise AssertionError("uninstalled selector must fail closed")
