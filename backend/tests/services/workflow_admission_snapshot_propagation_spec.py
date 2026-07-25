from backend.app.services.workflow.tool_execution import build_tool_inputs


def test_runtime_workflow_propagates_root_snapshot_to_each_tool_step() -> None:
    snapshot = {
        "workspace_id": "workspace-one",
        "root_execution_id": "execution-one",
        "snapshot_hash": "a" * 64,
    }

    tool_inputs = build_tool_inputs(
        tool_id="ig.ig_analyze_reference",
        resolved_inputs={
            "reference_id": "reference-one",
            "execution_admission_snapshot": {
                "snapshot_hash": "untrusted-step-value",
            },
        },
        profile_id="profile-one",
        playbook_inputs={"execution_admission_snapshot": snapshot},
    )

    assert tool_inputs["execution_admission_snapshot"] is snapshot
    assert tool_inputs["root_execution_id"] == "execution-one"
    assert tool_inputs["reference_id"] == "reference-one"


def test_runtime_workflow_without_root_snapshot_keeps_legacy_tool_payload() -> None:
    tool_inputs = build_tool_inputs(
        tool_id="core_llm.multimodal_analyze",
        resolved_inputs={"prompt": "analyze"},
        profile_id="profile-one",
        playbook_inputs={"playbook_code": "demo"},
    )

    assert tool_inputs == {
        "prompt": "analyze",
        "profile_id": "profile-one",
    }
