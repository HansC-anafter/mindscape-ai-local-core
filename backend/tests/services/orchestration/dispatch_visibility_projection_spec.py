from types import SimpleNamespace

from backend.app.models.phase_attempt import PhaseAttempt
from backend.app.services.orchestration.dispatch_orchestrator_core.attempt_reason_projection import (
    attach_attempt_reason_projection,
)
from backend.app.services.orchestration.meeting.dispatch_visibility import (
    build_gate_visibility,
    record_dispatch_visibility,
)


def test_gate_visibility_projects_dispatch_decisions():
    gate_result = SimpleNamespace(
        dispatch_intents=["intent-a"],
        clarify_intents=[SimpleNamespace(intent_id="intent-b", reason="needs input")],
        deferred_intents=[],
        shrunk_intents=[],
    )

    visibility = build_gate_visibility(
        gate_result,
        dispatchable_count=1,
        forced_dispatch_intent_ids={"intent-c"},
    )

    assert visibility["milestone"] == "dispatch_gate_evaluated"
    assert visibility["dispatch_intent_ids"] == ["intent-a"]
    assert visibility["clarify"] == [{"intent_id": "intent-b", "reason": "needs input"}]
    assert visibility["forced_dispatch_intent_ids"] == ["intent-c"]


def test_record_dispatch_visibility_keeps_session_metadata_append_only():
    session = SimpleNamespace(metadata={})

    record_dispatch_visibility(session, {"milestone": "one"})
    record_dispatch_visibility(session, {"milestone": "two"})

    assert session.metadata["dispatch_visibility"] == [
        {"milestone": "one"},
        {"milestone": "two"},
    ]


def test_attempt_reason_projection_attaches_engine_and_idempotency():
    phase = SimpleNamespace(id="phase-1", name="Run pack")
    attempt = PhaseAttempt(task_ir_id="task-ir-1", phase_id="phase-1")
    attempt.mark_dispatched(
        engine="playbook:ig_analyze_following",
        playbook_code="ig_analyze_following",
        target_workspace_id="ws-1",
    )

    payload = attach_attempt_reason_projection(
        {"status": "completed", "workspace_id": "ws-1"},
        phase=phase,
        action_item={"title": "Run pack"},
        attempt=attempt,
        engine="playbook:ig_analyze_following",
        target_workspace_id="ws-1",
        status="completed",
        reason="playbook_launched",
        playbook_code="ig_analyze_following",
        result={"execution_id": "exec-1"},
    )

    projection = payload["dispatch_attempt_reason"]
    assert projection["phase_id"] == "phase-1"
    assert projection["reason"] == "playbook_launched"
    assert projection["playbook_code"] == "ig_analyze_following"
    assert projection["execution_id"] == "exec-1"
    assert projection["idempotency_key"] == "task-ir-1:phase-1:1"
