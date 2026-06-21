from types import SimpleNamespace

from workflow_evidence_prompt_context_test_support import (
    Artifact,
    ArtifactType,
    IntentLog,
    LensPatch,
    PatchStatus,
    PrimaryActionType,
    StageResult,
    Task,
    TaskStatus,
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


def test_build_workflow_evidence_context_renders_recent_sections():
    task = Task(
        id="task-001",
        workspace_id="ws-001",
        message_id="msg-001",
        execution_id="exec-001",
        pack_id="brand.identity",
        task_type="execution",
        status=TaskStatus.SUCCEEDED,
        params={"title": "Refresh the brand direction board"},
        result={
            "summary": "Selected three reference directions for the next brand board.",
            "execution_trace": {
                "trace_id": "trace-001",
                "output_summary": "Clustered references and highlighted two dominant directions.",
            },
        },
        execution_context={"thread_id": "thread-001"},
        created_at=_utc_now(),
        next_eligible_at=_utc_now(),
    )
    artifact = Artifact(
        id="artifact-001",
        workspace_id="ws-001",
        execution_id="exec-001",
        thread_id="thread-001",
        playbook_code="brand.identity",
        artifact_type=ArtifactType.DRAFT,
        title="Brand Board Candidate",
        summary="A condensed board with three viable visual directions.",
        content={},
        storage_ref="/tmp/artifact",
        sync_state=None,
        primary_action_type=PrimaryActionType.PREVIEW,
        metadata={"landing": {"attachments_count": 2}},
    )
    stage_result = StageResult(
        id="stage-001",
        execution_id="exec-001",
        step_id="step-001",
        stage_name="reference_cluster",
        result_type="summary",
        content={"summary": "Six clusters reduced to three candidate directions."},
        preview="Three clusters retained after visual review.",
        requires_review=True,
        review_status="pending",
        artifact_id="artifact-001",
        created_at=_utc_now(),
    )
    intent_log = IntentLog(
        id="intent-001",
        raw_input="Pull together stronger references for the next brand pass.",
        channel="local_chat",
        profile_id="profile-001",
        project_id="proj-001",
        workspace_id="ws-001",
        pipeline_steps={},
        final_decision={"playbook_code": "brand.identity"},
        user_override=None,
        metadata={},
    )
    lens_patch = LensPatch(
        id="patch-001",
        lens_id="lens-001",
        meeting_session_id="meeting-prev",
        delta={"narrative_cohesion": {"before": "keep", "after": "emphasize"}},
        confidence=0.83,
        status=PatchStatus.APPROVED,
    )
    meeting = SimpleNamespace(
        workspace=SimpleNamespace(id="ws-001"),
        session=SimpleNamespace(workspace_id="ws-001", project_id="proj-001", thread_id="thread-001"),
        project_id="proj-001",
        thread_id="thread-001",
        tasks_store=_FakeTasksStore([task]),
        _artifacts_store_for_evidence=_FakeArtifactsStore({"exec-001": artifact}),
        _stage_results_store_for_evidence=_FakeStageResultsStore({"exec-001": [stage_result]}),
        _intent_logs_store_for_evidence=_FakeIntentLogsStore([intent_log]),
        _governance_store_for_evidence=_FakeGovernanceStore(
            {
                "exec-001": [
                    {
                        "approved": True,
                        "layer": "policy",
                        "reason": "Approved after visual quality review.",
                        "playbook_code": "brand.identity",
                    }
                ]
            }
        ),
        _lens_patch_store_for_evidence=_FakeLensPatchStore(lens_patch),
        _effective_lens=SimpleNamespace(global_preset_id="lens-001"),
    )

    context = build_workflow_evidence_context(meeting)

    assert "Recent execution outcomes:" in context
    assert "brand.identity" in context
    assert "trace=yes" in context
    assert "Recent stage checkpoints:" in context
    assert "reference_cluster/summary" in context
    assert "Recent artifacts:" in context
    assert "attachments=2" in context
    assert "Recent governance outcomes:" in context
    assert "Approved after visual quality review." in context
    assert "Recent intent routing:" in context
    assert "route=brand.identity" in context
    assert "Latest lens continuity signal:" in context
    assert "narrative_cohesion" in context


def test_command_bounded_workflow_evidence_does_not_fallback_to_project_scope():
    project_task = _make_task(
        task_id="task-project",
        execution_id="exec-project",
        summary="Old project execution that must not enter this E2E meeting.",
    )
    intent_log = IntentLog(
        id="intent-old",
        raw_input="Old project route that must not enter this E2E meeting.",
        channel="local_chat",
        profile_id="profile-001",
        project_id="proj-001",
        workspace_id="ws-001",
        pipeline_steps={},
        final_decision={"playbook_code": "old.playbook"},
        user_override=None,
        metadata={},
    )
    lens_patch = LensPatch(
        id="patch-old",
        lens_id="lens-001",
        meeting_session_id="meeting-old",
        delta={"old": {"before": "x", "after": "y"}},
        confidence=0.9,
        status=PatchStatus.APPROVED,
    )
    meeting = SimpleNamespace(
        workspace=SimpleNamespace(id="ws-001"),
        session=SimpleNamespace(
            workspace_id="ws-001",
            project_id="proj-001",
            thread_id="thread-new",
            meeting_type="e2e_validation",
            agenda=["Create a selected reference 90s storyboard E2E"],
            metadata={},
        ),
        project_id="proj-001",
        thread_id="thread-new",
        tasks_store=_FakeTasksStore(
            [],
            project_tasks=[project_task],
            workspace_tasks=[project_task],
        ),
        _artifacts_store_for_evidence=_FakeArtifactsStore({}),
        _stage_results_store_for_evidence=_FakeStageResultsStore({}),
        _intent_logs_store_for_evidence=_FakeIntentLogsStore([intent_log]),
        _governance_store_for_evidence=_FakeGovernanceStore({}),
        _lens_patch_store_for_evidence=_FakeLensPatchStore(lens_patch),
        _effective_lens=SimpleNamespace(global_preset_id="lens-001"),
    )

    context = build_workflow_evidence_context(meeting)

    assert context == ""
    assert meeting._workflow_evidence_diagnostics["scope"] == "thread_bounded_empty"
    assert meeting._workflow_evidence_diagnostics["total_candidate_count"] == 0
