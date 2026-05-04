from backend.app.models.meeting_command import MeetingCommandRecord, MeetingCommandStatus
from backend.app.services.meeting_execution_graph_commands import (
    project_command_ledger_graph,
)


def test_command_ledger_graph_preserves_meeting_orchestration_metadata():
    command = MeetingCommandRecord(
        command_id="cmd_graph",
        workspace_id="ws_demo",
        meeting_id="mtg_demo",
        thread_id="thread_demo",
        origin_surface="meeting_workbench",
        actor="user",
        intent_text="Use AOL refs",
        status=MeetingCommandStatus.FAILED,
        metadata={
            "dispatch_status": "failed",
            "dispatch_mode": "route_meeting_orchestration",
            "meeting_orchestration": {
                "status": "failed",
                "error_code": "meeting_orchestration_timeout",
                "task_ir_id": None,
                "artifact_landing_status": "failed",
                "review_state": "needs_revision",
                "review_reason": "producer_eval_requires_review",
                "recommended_actions": [
                    "rewrite_storyboard_script_with_reference_cues"
                ],
                "producer_quality_gate": {
                    "schema_version": "meeting_producer_quality_gate.v1",
                    "gate_state": "blocked_for_revision",
                    "decision": "rewrite_required",
                },
                "request_contract_aol_metadata": {
                    "selected_object_refs": [
                        {"uri": "mindscape://ig/reference/ref_a"},
                        {"uri": "mindscape://ig/reference/ref_b"},
                    ],
                    "candidate_playbooks": [
                        {
                            "pack_code": "story_direction",
                            "playbook_code": "director_guidance",
                        }
                    ],
                },
            },
        },
    )

    projection = project_command_ledger_graph([command])

    [node] = projection.nodes
    assert node["status"] == "error"
    assert node["metadata"]["dispatch_status"] == "failed"
    assert node["metadata"]["dispatch_mode"] == "route_meeting_orchestration"
    assert (
        node["metadata"]["meeting_orchestration_error_code"]
        == "meeting_orchestration_timeout"
    )
    assert node["metadata"]["artifact_landing_status"] == "failed"
    assert node["metadata"]["review_state"] == "needs_revision"
    assert node["metadata"]["producer_quality_gate"]["decision"] == (
        "rewrite_required"
    )
    assert (
        len(
            node["metadata"]["request_contract_aol_metadata"][
                "selected_object_refs"
            ]
        )
        == 2
    )
