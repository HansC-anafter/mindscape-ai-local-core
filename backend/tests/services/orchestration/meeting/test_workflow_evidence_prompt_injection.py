from workflow_evidence_prompt_context_test_support import AgentDefinition, _PromptHarness


def test_build_turn_prompt_injects_workflow_evidence_block():
    harness = _PromptHarness(
        workflow_evidence_context=(
            "Use these recent workflow materials as supporting evidence when they help the meeting agenda.\n"
            "Recent execution outcomes:\n"
            "  - [succeeded] brand.identity exec=exec-001 trace=yes :: Direction shortlist prepared"
        )
    )

    prompt = harness._build_turn_prompt(
        role_id="facilitator",
        round_num=1,
        user_message="Review the latest brand direction evidence.",
        decision=None,
        planner_proposals=[],
        critic_notes=[],
    )

    assert "=== Workflow Evidence ===" in prompt
    assert "Direction shortlist prepared" in prompt
    assert "=== End Workflow Evidence ===" in prompt


def test_full_review_native_spatial_prompt_uses_minimal_context_and_non_native_planner_directive():
    harness = _PromptHarness(
        workflow_evidence_context=(
            "Use these recent workflow materials as supporting evidence when they help the meeting agenda.\n"
            "Recent execution outcomes:\n"
            "  - [succeeded] brand.identity exec=exec-001 trace=yes :: Direction shortlist prepared"
        )
    )
    harness._full_review_required = True
    harness._asset_map_context = "ws-asset-map"
    harness._project_context = "project-summary"
    harness._uploaded_files = [{"file_name": "handoff.png", "file_type": "image/png"}]

    prompt = harness._build_turn_prompt(
        role_id="planner",
        round_num=1,
        user_message="Design a spatial handoff scene for Blender downstream playback.",
        decision=None,
        planner_proposals=[],
        critic_notes=[],
    )

    assert "=== Workspace Asset Map ===" not in prompt
    assert "=== Workflow Evidence ===" not in prompt
    assert "=== Contract Deliverables ===" not in prompt
    assert "=== Uploaded Files ===" not in prompt
    assert "sole spatial planning decision-maker" not in prompt
    assert "Output ONE final JSON object that can drive downstream spatial execution." not in prompt
    assert "structured program draft in JSON" not in prompt
    assert "As planner, output ONE JSON object describing a bounded spatial planning proposal" in prompt
    assert "Required top-level keys: decision_summary, actors, objects, anchors" in prompt


def test_full_review_native_spatial_system_message_overrides_generic_planner_style():
    harness = _PromptHarness(workflow_evidence_context="")
    harness._full_review_required = True
    role_def = AgentDefinition(
        agent_id="planner",
        agent_name="Planner",
        role="planner",
        system_prompt="You propose practical plans, steps, and evidence for execution.",
        tools=["workspace_query"],
        responsibility_boundary="proposal_and_planning",
        critical_rules=["Every step must have a clear owner and measurable outcome."],
        communication_style="Structured planner. Use numbered steps with ownership and deliverables.",
        success_metrics=["Plan has concrete, executable steps with clear ownership."],
        capability_profile="precise",
    )

    system_message = harness._assemble_system_message(
        role_def,
        role_id="planner",
        user_message="Design a spatial handoff scene for Blender downstream playback.",
    )

    assert "You design bounded spatial planning proposals for downstream replay and staging." in system_message
    assert "Spatial scene planner. Produce compact machine-readable JSON for spatial execution." in system_message
    assert "Structured planner. Use numbered steps with ownership and deliverables." not in system_message
