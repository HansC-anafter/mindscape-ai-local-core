from datetime import timedelta

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.task_admission_service import (
    AdmissionPressure,
    TaskAdmissionService,
)


def _build_task(*, visibility: str = "background", auto_triggered: bool = True) -> Task:
    return Task(
        id=f"task-{visibility}",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id=f"exec-{visibility}",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="ig_analysis",
        created_at=_utc_now(),
        execution_context={
            "auto_triggered": auto_triggered,
            "admission_policy": {
                "mode": "auto" if auto_triggered else "manual",
                "visibility": visibility,
                "producer_kind": "pin_reference",
            },
        },
    )


def test_manual_task_bypasses_admission_defer(monkeypatch):
    service = TaskAdmissionService()
    task = _build_task(auto_triggered=False)

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setattr(
        service,
        "_load_queue_pressure",
        lambda *_args, **_kwargs: AdmissionPressure(
            queue_shard="ig_analysis",
            pending_total=999,
            running_total=4,
            oldest_pending_at=_utc_now() - timedelta(hours=1),
        ),
    )

    decision = service.evaluate_on_create(object(), task)

    assert decision.allow is True


def test_auto_task_deferred_when_shard_over_budget(monkeypatch):
    service = TaskAdmissionService()
    task = _build_task()

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_PENDING_LIMIT", "10")
    monkeypatch.setattr(
        service,
        "_load_queue_pressure",
        lambda *_args, **_kwargs: AdmissionPressure(
            queue_shard="ig_analysis",
            pending_total=25,
            running_total=2,
            oldest_pending_at=_utc_now() - timedelta(seconds=10),
        ),
    )

    decision = service.evaluate_on_create(object(), task)

    assert decision.allow is False
    assert decision.next_eligible_at is not None
    assert decision.blocked_payload["reason"] == "pending_limit"
    assert decision.execution_context["admission"]["state"] == "deferred"
    assert (
        decision.execution_context["resume_after"]
        == decision.next_eligible_at.isoformat()
    )


def test_visible_auto_ranks_above_background_auto(monkeypatch):
    service = TaskAdmissionService()
    background_task = _build_task(visibility="background")
    visible_task = _build_task(visibility="visible")

    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_ENABLED", "1")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_PENDING_LIMIT", "100")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_BACKGROUND_PENDING_LIMIT_MULTIPLIER", "1")
    monkeypatch.setenv("LOCAL_CORE_TASK_ADMISSION_VISIBLE_PENDING_LIMIT_MULTIPLIER", "2")
    monkeypatch.setattr(
        service,
        "_load_queue_pressure",
        lambda *_args, **_kwargs: AdmissionPressure(
            queue_shard="ig_analysis",
            pending_total=150,
            running_total=1,
            oldest_pending_at=None,
        ),
    )

    background_decision = service.evaluate_on_create(object(), background_task)
    visible_decision = service.evaluate_on_create(object(), visible_task)

    assert background_decision.allow is False
    assert visible_decision.allow is True
