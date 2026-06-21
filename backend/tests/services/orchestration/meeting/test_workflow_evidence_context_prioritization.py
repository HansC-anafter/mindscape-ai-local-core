from types import SimpleNamespace

from workflow_evidence_prompt_context_test_support import (
    IntentLog,
    StageResult,
    _FakeArtifactsStore,
    _FakeGovernanceStore,
    _FakeIntentLogsStore,
    _FakeLensPatchStore,
    _FakeStageResultsStore,
    _FakeTasksStore,
    _make_task,
    _utc_now,
    build_workflow_evidence_context,
)


def test_review_meeting_prioritizes_stage_and_governance_sections():
    review_task = _make_task(
        task_id="task-review",
        execution_id="exec-review",
        summary="Review batch prepared for brand direction.",
        trace=True,
    )
    intent_log = IntentLog(
        id="intent-review",
        raw_input="Review the latest brand direction batch.",
        channel="local_chat",
        profile_id="profile-001",
        project_id="proj-001",
        workspace_id="ws-001",
        pipeline_steps={"routing": "done"},
        final_decision={"playbook_code": "brand.identity"},
        metadata={},
    )
    strong_stage = StageResult(
        id="stage-strong",
        execution_id="exec-review",
        step_id="step-1",
        stage_name="cluster_review",
        result_type="summary",
        content={"summary": "Two clusters need explicit review before selection."},
        preview="Pending review on two shortlisted clusters.",
        requires_review=True,
        review_status="pending",
        artifact_id="artifact-1",
        created_at=_utc_now(),
    )
    weak_stage = StageResult(
        id="stage-weak",
        execution_id="exec-review",
        step_id="step-2",
        stage_name="ingest",
        result_type="log",
        content={"message": "Ingest complete."},
        preview="Ingest complete.",
        requires_review=False,
        review_status=None,
        artifact_id=None,
        created_at=_utc_now(),
    )
    meeting = SimpleNamespace(
        workspace=SimpleNamespace(id="ws-001"),
        session=SimpleNamespace(
            workspace_id="ws-001",
            project_id="proj-001",
            thread_id="thread-001",
            meeting_type="review",
            agenda=["Review the latest workflow evidence"],
        ),
        project_id="proj-001",
        thread_id="thread-001",
        tasks_store=_FakeTasksStore([review_task]),
        _artifacts_store_for_evidence=_FakeArtifactsStore({}),
        _stage_results_store_for_evidence=_FakeStageResultsStore(
            {"exec-review": [weak_stage, strong_stage]}
        ),
        _intent_logs_store_for_evidence=_FakeIntentLogsStore([intent_log]),
        _governance_store_for_evidence=_FakeGovernanceStore(
            {
                "exec-review": [
                    {
                        "approved": False,
                        "layer": "policy",
                        "reason": "Requires human review before promotion.",
                        "playbook_code": "brand.identity",
                    }
                ]
            }
        ),
        _lens_patch_store_for_evidence=_FakeLensPatchStore(None),
        _effective_lens=SimpleNamespace(global_preset_id="lens-001"),
    )

    context = build_workflow_evidence_context(meeting)

    assert context.index("Recent stage checkpoints:") < context.index(
        "Recent execution outcomes:"
    )
    stage_section = context.split("Recent stage checkpoints:\n", 1)[1].split(
        "\nRecent governance outcomes:",
        1,
    )[0]
    assert "cluster_review/summary review=pending" in stage_section
    assert stage_section.splitlines()[0].startswith(
        "  - cluster_review/summary review=pending"
    )


def test_decision_meeting_prioritizes_governance_and_override_intent_logs():
    task_a = _make_task(
        task_id="task-a",
        execution_id="exec-a",
        summary="Direction shortlist prepared.",
    )
    task_b = _make_task(
        task_id="task-b",
        execution_id="exec-b",
        summary="Fallback batch prepared.",
    )
    plain_log = IntentLog(
        id="intent-plain",
        raw_input="Route a generic request.",
        channel="local_chat",
        profile_id="profile-001",
        project_id="proj-001",
        workspace_id="ws-001",
        pipeline_steps={},
        final_decision={"playbook_code": "brand.identity"},
        metadata={},
    )
    override_log = IntentLog(
        id="intent-override",
        raw_input="Choose the direction that should go into the main board.",
        channel="local_chat",
        profile_id="profile-001",
        project_id="proj-001",
        workspace_id="ws-001",
        pipeline_steps={"routing": "done"},
        final_decision={
            "playbook_code": "brand.identity",
            "requires_user_approval": True,
        },
        user_override={"playbook_code": "brand.identity"},
        metadata={},
    )
    meeting = SimpleNamespace(
        workspace=SimpleNamespace(id="ws-001"),
        session=SimpleNamespace(
            workspace_id="ws-001",
            project_id="proj-001",
            thread_id="thread-001",
            meeting_type="decision",
            agenda=["Choose the next direction"],
        ),
        project_id="proj-001",
        thread_id="thread-001",
        tasks_store=_FakeTasksStore([task_a, task_b]),
        _artifacts_store_for_evidence=_FakeArtifactsStore({}),
        _stage_results_store_for_evidence=_FakeStageResultsStore({}),
        _intent_logs_store_for_evidence=_FakeIntentLogsStore([plain_log, override_log]),
        _governance_store_for_evidence=_FakeGovernanceStore(
            {
                "exec-a": [
                    {
                        "approved": False,
                        "layer": "policy",
                        "reason": "Decision requires explicit approval.",
                        "playbook_code": "brand.identity",
                    }
                ]
            }
        ),
        _lens_patch_store_for_evidence=_FakeLensPatchStore(None),
        _effective_lens=SimpleNamespace(global_preset_id="lens-001"),
    )

    context = build_workflow_evidence_context(meeting)

    assert context.index("Recent governance outcomes:") < context.index(
        "Recent execution outcomes:"
    )
    intent_section = context.split("Recent intent routing:\n", 1)[1].split(
        "\nLatest lens continuity signal:",
        1,
    )[0]
    assert intent_section.splitlines()[0].startswith(
        "  - [local_chat] route=brand.identity override=yes"
    )


def test_workflow_evidence_context_records_scope_fallback_and_budget_diagnostics():
    project_task = _make_task(
        task_id="task-project",
        execution_id="exec-project",
        summary="Project-level evidence packet candidate.",
    )
    meeting = SimpleNamespace(
        workspace=SimpleNamespace(id="ws-001"),
        session=SimpleNamespace(
            workspace_id="ws-001",
            project_id="proj-001",
            thread_id="thread-001",
            meeting_type="decision",
            agenda=["Choose the next direction"],
        ),
        project_id="proj-001",
        thread_id="thread-001",
        tasks_store=_FakeTasksStore([], project_tasks=[project_task]),
        _artifacts_store_for_evidence=_FakeArtifactsStore({}),
        _stage_results_store_for_evidence=_FakeStageResultsStore({}),
        _intent_logs_store_for_evidence=_FakeIntentLogsStore([]),
        _governance_store_for_evidence=_FakeGovernanceStore({}),
        _lens_patch_store_for_evidence=_FakeLensPatchStore(None),
        _effective_lens=SimpleNamespace(global_preset_id="lens-001"),
    )

    context = build_workflow_evidence_context(meeting)
    diagnostics = meeting._workflow_evidence_diagnostics

    assert "Recent execution outcomes:" in context
    assert diagnostics["profile"] == "decision"
    assert diagnostics["scope"] == "project"
    assert diagnostics["total_line_budget"] == 8
    assert diagnostics["total_candidate_count"] >= 1
    assert diagnostics["total_dropped_count"] == 0
    assert diagnostics["selected_counts"]["Recent execution outcomes"] >= 1
    assert diagnostics["dropped_counts"]["Recent execution outcomes"] == 0
    assert diagnostics["budget_utilization_ratio"] > 0
    assert diagnostics["rendered"] is True
