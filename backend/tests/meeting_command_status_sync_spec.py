from types import SimpleNamespace

from backend.app.models.meeting_command import (
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.services.meeting_command_status_sync import (
    sync_meeting_command_from_task,
    sync_meeting_command_from_agent_result,
)


class _FakeMeetingCommandStore:
    def __init__(self, command):
        self.command = command
        self.saved = None

    def get(self, command_id):
        if command_id == self.command.command_id:
            return self.command
        return None

    def save(self, command):
        self.saved = command
        return command


def test_sync_meeting_command_from_late_agent_result_recovers_timeout(monkeypatch):
    class _FakeArtifactStore:
        def get_by_execution_id(self, execution_id):
            assert execution_id == "exec-late"
            return SimpleNamespace(
                id="artifact-db-1",
                storage_ref="/workspace/artifacts/exec-late",
            )

    monkeypatch.setattr(
        "backend.app.services.stores.postgres.artifacts_store.PostgresArtifactsStore",
        lambda: _FakeArtifactStore(),
    )
    command = MeetingCommandRecord(
        command_id="cmd-late",
        workspace_id="ws-1",
        meeting_id="mtg-1",
        thread_id="thread-1",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Generate the IG content",
        status=MeetingCommandStatus.FAILED,
        metadata={
            "dispatch_status": "failed",
            "meeting_orchestration": {
                "status": "failed",
                "completion_status": "failed",
                "error_code": "meeting_orchestration_timeout",
                "artifact_landing_status": "pending",
                "late_result_possible": True,
                "request_contract_aol_metadata": {
                    "command_id": "cmd-late",
                    "selected_object_refs": [{"uri": "mindscape://ig/ref/a"}],
                },
            },
        },
    )
    store = _FakeMeetingCommandStore(command)

    updated = sync_meeting_command_from_agent_result(
        execution_id="exec-late",
        result={
            "execution_id": "exec-late",
            "status": "completed",
            "output": "done",
            "metadata": {
                "meeting_command_id": "cmd-late",
                "addressable_object_layer": {"command_id": "cmd-late"},
            },
        },
        governance_result={"success": True, "artifact_id": "artifact-db-1"},
        status="completed",
        store=store,
    )

    assert updated is store.saved
    assert updated.status == MeetingCommandStatus.COMPLETED
    assert updated.accepted_task_id == "exec-late"
    assert updated.metadata["dispatch_status"] == "completed_late"
    orchestration = updated.metadata["meeting_orchestration"]
    assert orchestration["status"] == "completed"
    assert orchestration["completion_status"] == "completed"
    assert orchestration["artifact_db_ids"] == ["artifact-db-1"]
    assert orchestration["artifact_file_paths"] == ["/workspace/artifacts/exec-late"]
    assert orchestration["artifact_landing_status"] == "landed_late"
    assert orchestration["late_result_reconciled"] is True
    assert orchestration["recovered_from_error_code"] == "meeting_orchestration_timeout"
    assert "error_code" not in orchestration


def test_late_agent_result_preserves_producer_quality_gate_for_revision():
    command = MeetingCommandRecord(
        command_id="cmd-quality-late",
        workspace_id="ws-1",
        meeting_id="mtg-1",
        thread_id="thread-1",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Run storyboard orchestration",
        status=MeetingCommandStatus.FAILED,
        metadata={
            "dispatch_mode": "route_meeting_orchestration",
            "dispatch_status": "failed",
            "meeting_orchestration": {
                "status": "failed",
                "completion_status": "failed",
                "error_code": "meeting_orchestration_timeout",
                "artifact_landing_status": "pending",
                "late_result_possible": True,
            },
        },
    )
    store = _FakeMeetingCommandStore(command)

    updated = sync_meeting_command_from_agent_result(
        execution_id="exec-quality-late",
        result={
            "execution_id": "exec-quality-late",
            "status": "completed",
            "metadata": {"meeting_command_id": "cmd-quality-late"},
            "output": {
                "producer_eval_summary": {
                    "schema_version": "producer_eval_summary.v1",
                    "producer": "performance_direction",
                    "pack_code": "performance_direction",
                    "playbook_code": "pd_storyboard_gen",
                    "passed": False,
                    "review_state": "needs_revision",
                    "rewrite_recommended": True,
                    "rewrite_dispatch_request": {
                        "schema_version": (
                            "producer_quality_rewrite_dispatch_request.v1"
                        ),
                        "pack_code": "performance_direction",
                        "playbook_code": "pd_storyboard_content_rewrite",
                    },
                    "recommended_actions": [
                        "rewrite_storyboard_script_with_reference_cues"
                    ],
                }
            },
        },
        governance_result={"success": True, "artifact_id": "artifact-quality-late"},
        status="completed",
        store=store,
    )

    assert updated is store.saved
    orchestration = updated.metadata["meeting_orchestration"]
    assert orchestration["status"] == "completed"
    assert orchestration["completion_status"] == "needs_revision"
    assert orchestration["review_state"] == "needs_revision"
    assert orchestration["review_reason"] == "producer_eval_requires_review"
    assert orchestration["producer_quality_gate"]["gate_state"] == (
        "blocked_for_revision"
    )
    assert orchestration["producer_quality_gate"]["llm_review_status"] == "fallback"
    assert orchestration["producer_quality_gate"]["rewrite_handoff"]["kind"] == (
        "producer_quality_rewrite_handoff"
    )
    dispatch_request = orchestration["producer_quality_gate"]["rewrite_handoff"][
        "dispatch_request"
    ]
    assert dispatch_request["playbook_code"] == "pd_storyboard_content_rewrite"
    assert dispatch_request["dispatch_mode"] == "explicit_quality_requirement_required"


def test_task_sync_does_not_demote_meeting_orchestration_command():
    command = MeetingCommandRecord(
        command_id="cmd-orchestrated",
        workspace_id="ws-1",
        meeting_id="mtg-1",
        thread_id="thread-1",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Run orchestration",
        status=MeetingCommandStatus.COMPLETED,
        accepted_task_id="task-ir-1",
        metadata={
            "dispatch_mode": "route_meeting_orchestration",
            "dispatch_status": "completed",
            "meeting_orchestration": {
                "status": "completed",
                "task_ir_id": "task-ir-1",
            },
        },
    )
    store = _FakeMeetingCommandStore(command)
    internal_phase_task = SimpleNamespace(
        id="phase-task-1",
        execution_id="phase-exec-1",
        status="failed",
        pack_id="internal_phase_pack",
        task_type="playbook_execution",
        completed_at=None,
        error="Workflow completed with step errors",
        params={"meeting_command_id": "cmd-orchestrated"},
        result=None,
        execution_context={"task_ir_id": "task-ir-1", "phase_id": "phase_4"},
    )

    updated = sync_meeting_command_from_task(internal_phase_task, store=store)

    assert updated is None
    assert store.saved is None
    assert command.status == MeetingCommandStatus.COMPLETED
    assert command.metadata["dispatch_status"] == "completed"


def test_late_agent_result_does_not_demote_completed_meeting_orchestration_command():
    command = MeetingCommandRecord(
        command_id="cmd-orchestrated",
        workspace_id="ws-1",
        meeting_id="mtg-1",
        thread_id="thread-1",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Run orchestration",
        status=MeetingCommandStatus.COMPLETED,
        accepted_task_id="task-ir-1",
        metadata={
            "dispatch_mode": "route_meeting_orchestration",
            "dispatch_status": "completed",
            "meeting_orchestration": {
                "status": "completed",
                "task_ir_id": "task-ir-1",
                "artifact_landing_status": "landed",
            },
        },
    )
    store = _FakeMeetingCommandStore(command)

    updated = sync_meeting_command_from_agent_result(
        execution_id="internal-exec-1",
        result={
            "execution_id": "internal-exec-1",
            "status": "failed",
            "error": "internal phase failed after parent completed",
            "metadata": {"meeting_command_id": "cmd-orchestrated"},
        },
        status="failed",
        store=store,
    )

    assert updated is None
    assert store.saved is None
    assert command.status == MeetingCommandStatus.COMPLETED
    assert command.accepted_task_id == "task-ir-1"
    assert command.metadata["dispatch_status"] == "completed"
    assert command.metadata["meeting_orchestration"]["artifact_landing_status"] == "landed"
