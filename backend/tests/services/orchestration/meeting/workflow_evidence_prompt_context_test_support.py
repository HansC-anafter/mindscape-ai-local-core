from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.models.lens_patch import LensPatch, PatchStatus
from backend.app.models.mindscape import IntentLog
from backend.app.models.playbook import AgentDefinition
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
        self.executor_runtime = "codex_cli"
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
        self._full_review_required = False

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

    def _requires_full_deliberation_review(self) -> bool:
        return self._full_review_required


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
