from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.models.lens_patch import LensPatch, PatchStatus
from backend.app.models.mindscape import IntentLog
from backend.app.models.workspace import (
    Artifact,
    ArtifactType,
    PrimaryActionType,
    Task,
    TaskStatus,
)
from backend.app.services.orchestration.meeting._prompt_context import (
    build_workflow_evidence_context,
)
from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin
from backend.app.services.stores.stage_results_store import StageResult


class _FakeArtifactsStore:
    def __init__(self, artifacts_by_execution):
        self.artifacts_by_execution = artifacts_by_execution

    def get_by_execution_id(self, execution_id: str):
        return self.artifacts_by_execution.get(execution_id)


class _FakeStageResultsStore:
    def __init__(self, stage_results_by_execution):
        self.stage_results_by_execution = stage_results_by_execution

    def list_stage_results(self, execution_id: str, limit: int = 2):
        return list(self.stage_results_by_execution.get(execution_id, []))[:limit]


class _FakeIntentLogsStore:
    def __init__(self, logs):
        self.logs = logs

    def list_intent_logs(self, **kwargs):
        limit = kwargs.get("limit")
        logs = list(self.logs)
        return logs[:limit] if isinstance(limit, int) else logs


class _FakeGovernanceStore:
    def __init__(self, decisions_by_execution):
        self.decisions_by_execution = decisions_by_execution

    def list_decisions_for_execution(self, *, workspace_id: str, execution_id: str, limit: int = 2):
        return list(self.decisions_by_execution.get(execution_id, []))[:limit]


class _FakeLensPatchStore:
    def __init__(self, patch):
        self.patch = patch

    def get_latest_for_lens(self, lens_id: str):
        return self.patch


class _FakeTasksStore:
    def __init__(self, tasks, project_tasks=None, workspace_tasks=None):
        self.tasks = tasks
        self.project_tasks = project_tasks or []
        self.workspace_tasks = workspace_tasks or []

    def list_tasks_by_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        limit: int = 6,
        exclude_cancelled: bool = True,
    ):
        return list(self.tasks)[:limit]

    def list_executions_by_project(
        self,
        *,
        workspace_id: str,
        project_id: str,
        limit: int = 8,
    ):
        return list(self.project_tasks)[:limit]

    def list_executions_by_workspace(
        self,
        *,
        workspace_id: str,
        limit: int = 8,
    ):
        return list(self.workspace_tasks)[:limit]


def _make_task(
    *,
    task_id: str,
    execution_id: str,
    status: TaskStatus = TaskStatus.SUCCEEDED,
    summary: str,
    trace: bool = False,
) -> Task:
    result = {"summary": summary}
    if trace:
        result["execution_trace"] = {
            "trace_id": f"trace-{execution_id}",
            "output_summary": summary,
        }
    return Task(
        id=task_id,
        workspace_id="ws-001",
        message_id=f"msg-{task_id}",
        execution_id=execution_id,
        pack_id="brand.identity",
        task_type="execution",
        status=status,
        params={"title": summary},
        result=result,
        execution_context={"thread_id": "thread-001"},
        created_at=_utc_now(),
        next_eligible_at=_utc_now(),
    )


class _PromptHarness(MeetingPromptsMixin):
    def __init__(self, workflow_evidence_context: str) -> None:
        self._locale = "en"
        self.project_id = "proj-001"
        self.profile_id = "profile-001"
        self._project_context = ""
        self._asset_map_context = ""
        self._uploaded_files = []
        self._turn_history = []
        self._active_intent_ids = []
        self._effective_lens = None
        self._workflow_evidence_context = workflow_evidence_context
        self.store = SimpleNamespace(list_intents=lambda profile_id, project_id=None: [])
        self.session = SimpleNamespace(
            id="meeting-001",
            workspace_id="ws-001",
            project_id="proj-001",
            max_rounds=4,
            agenda=["Review recent workflow materials"],
        )

    def _history_snippet(self) -> str:
        return "(none)"

    def _build_tool_inventory_block(self) -> str:
        return ""

    def _has_workspace_tool_bindings(self) -> bool:
        return False

    def _build_workspace_instruction_block(self) -> str:
        return ""

    def _build_previous_decisions_context(self) -> str:
        return ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
