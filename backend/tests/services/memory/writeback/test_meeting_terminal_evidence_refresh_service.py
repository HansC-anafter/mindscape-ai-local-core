from datetime import datetime, timezone

from app.models.workspace import Artifact, ArtifactType, PrimaryActionType, Task, TaskStatus
from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession, MeetingStatus
from backend.app.services.memory.writeback.meeting_terminal_evidence_refresh_service import (
    MeetingTerminalEvidenceRefreshService,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FakeMeetingSessionStore:
    def __init__(self, session: MeetingSession, decisions: list[MeetingDecision]) -> None:
        self.session = session
        self.decisions = decisions
        self.updated_session = None
        self.updated_decisions: list[MeetingDecision] = []

    def get_by_id(self, session_id: str):
        return self.session if self.session.id == session_id else None

    def update(self, session: MeetingSession):
        self.updated_session = session
        self.session = session
        return session

    def list_decisions_by_session(self, session_id: str):
        if session_id != self.session.id:
            return []
        return list(self.decisions)

    def update_decision(self, decision: MeetingDecision):
        for index, existing in enumerate(self.decisions):
            if existing.id == decision.id:
                self.decisions[index] = decision
                break
        self.updated_decisions.append(decision)
        return decision


class FakeArtifactStore:
    def __init__(self, artifact: Artifact | None) -> None:
        self.artifact = artifact

    def get_by_execution_id(self, execution_id: str):
        if self.artifact and self.artifact.execution_id == execution_id:
            return self.artifact
        return None


class FakeEvidenceLinkStore:
    def __init__(self) -> None:
        self.links = {}

    def upsert(self, link):
        key = (
            link.memory_item_id,
            link.evidence_type,
            link.evidence_id,
            link.link_role,
        )
        self.links[key] = link
        return link


def test_refresh_for_closed_session_backfills_terminal_task_and_artifact():
    session = MeetingSession(
        id="session-1",
        workspace_id="ws-1",
        project_id="proj-1",
        thread_id="thread-1",
        status=MeetingStatus.CLOSED,
        ended_at=_utc_now(),
        action_items=[
            {
                "title": "Write brief",
                "intent_id": "intent-1",
                "source_intent_id": "intent-1",
                "source_phase_id": "phase-1",
                "landing_status": "task_created",
            }
        ],
        metadata={"canonical_memory_item_id": "memory-1"},
    )
    decision = MeetingDecision(
        id="decision-1",
        session_id=session.id,
        workspace_id=session.workspace_id,
        category="action",
        content="Write brief",
        status="dispatched",
        source_action_item=dict(session.action_items[0]),
    )
    task = Task(
        id="task-1",
        workspace_id=session.workspace_id,
        message_id="attempt-1",
        execution_id=None,
        project_id=session.project_id,
        pack_id="openseo.save_to_markdown",
        task_type="tool_execution",
        status=TaskStatus.SUCCEEDED,
        params={},
        result={"summary": "partner_brief.md saved"},
        execution_context={
            "phase_id": "phase-1",
            "ir_provenance": {
                "phase_id": "phase-1",
                "source_intent_id": "intent-1",
            },
        },
        meeting_session_id=session.id,
        completed_at=_utc_now(),
    )
    artifact = Artifact(
        id="artifact-1",
        workspace_id=session.workspace_id,
        task_id=task.id,
        execution_id=task.id,
        thread_id=session.thread_id,
        playbook_code="external_agent",
        artifact_type=ArtifactType.DATA,
        title="partner_brief.md",
        summary="partner brief",
        content={},
        storage_ref="/tmp/artifacts/task-1",
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata={
            "landing": {
                "result_json_path": "/tmp/artifacts/task-1/result.json",
                "summary_md_path": "/tmp/artifacts/task-1/summary.md",
            }
        },
    )
    meeting_store = FakeMeetingSessionStore(session, [decision])
    evidence_store = FakeEvidenceLinkStore()
    service = MeetingTerminalEvidenceRefreshService(
        meeting_session_store=meeting_store,
        artifact_store=FakeArtifactStore(artifact),
        evidence_link_store=evidence_store,
    )

    result = service.refresh_for_task(task)

    assert result["refreshed"] is True
    assert result["matched_action_items"] == 1
    assert result["updated_decisions"] == 1
    assert result["links_upserted"] == 2

    updated_item = meeting_store.session.action_items[0]
    assert updated_item["task_id"] == "task-1"
    assert updated_item["execution_id"] == "task-1"
    assert updated_item["task_status"] == "succeeded"
    assert updated_item["artifact_id"] == "artifact-1"
    assert updated_item["artifact_path"] == "/tmp/artifacts/task-1"
    assert updated_item["result_json_path"] == "/tmp/artifacts/task-1/result.json"
    assert updated_item["summary_md_path"] == "/tmp/artifacts/task-1/summary.md"
    assert updated_item["landing_status"] == "task_created"

    updated_decision = meeting_store.decisions[0]
    assert updated_decision.status == "resolved"
    assert updated_decision.resolved_by_task_id == "task-1"
    assert updated_decision.source_action_item["artifact_id"] == "artifact-1"

    task_link = evidence_store.links[("memory-1", "task_execution", "task-1", "supports")]
    assert task_link.metadata["execution_id"] == "task-1"
    assert task_link.metadata["status"] == "succeeded"
    artifact_link = evidence_store.links[
        ("memory-1", "artifact_result", "artifact-1", "supports")
    ]
    assert artifact_link.metadata["execution_id"] == "task-1"
    decision_link = evidence_store.links[
        ("memory-1", "meeting_decision", "decision-1", "supports")
    ]
    assert decision_link.metadata["status"] == "resolved"
    assert decision_link.metadata["resolved_by_task_id"] == "task-1"


def test_refresh_for_closed_session_preserves_dispatch_status_for_failed_task():
    session = MeetingSession(
        id="session-2",
        workspace_id="ws-2",
        status=MeetingStatus.CLOSED,
        ended_at=_utc_now(),
        action_items=[
            {
                "title": "Run review",
                "intent_id": "intent-2",
                "source_intent_id": "intent-2",
                "source_phase_id": "phase-2",
                "landing_status": "task_created",
                "execution_id": "task-2",
            }
        ],
        metadata={"canonical_memory_item_id": "memory-2"},
    )
    decision = MeetingDecision(
        id="decision-2",
        session_id=session.id,
        workspace_id=session.workspace_id,
        category="action",
        content="Run review",
        status="dispatched",
        source_action_item=dict(session.action_items[0]),
    )
    task = Task(
        id="task-2",
        workspace_id=session.workspace_id,
        message_id="attempt-2",
        execution_id=None,
        pack_id="review.maybe_suggest_review",
        task_type="tool_execution",
        status=TaskStatus.FAILED,
        params={},
        result={},
        execution_context={
            "phase_id": "phase-2",
            "ir_provenance": {"source_intent_id": "intent-2"},
        },
        meeting_session_id=session.id,
        completed_at=_utc_now(),
        error="profile_id missing",
    )
    meeting_store = FakeMeetingSessionStore(session, [decision])
    evidence_store = FakeEvidenceLinkStore()
    service = MeetingTerminalEvidenceRefreshService(
        meeting_session_store=meeting_store,
        artifact_store=FakeArtifactStore(None),
        evidence_link_store=evidence_store,
    )

    result = service.refresh_for_task(task)

    assert result["refreshed"] is True
    updated_item = meeting_store.session.action_items[0]
    assert updated_item["landing_status"] == "task_created"
    assert updated_item["task_status"] == "failed"
    assert updated_item["task_error"] == "profile_id missing"

    updated_decision = meeting_store.decisions[0]
    assert updated_decision.status == "dispatched"
    assert updated_decision.resolved_by_task_id is None

    task_link = evidence_store.links[("memory-2", "task_execution", "task-2", "supports")]
    assert task_link.metadata["execution_id"] == "task-2"
    assert task_link.metadata["status"] == "failed"
    assert ("memory-2", "artifact_result", "artifact-1", "supports") not in evidence_store.links


def test_refresh_skips_active_sessions():
    session = MeetingSession(
        id="session-3",
        workspace_id="ws-3",
        status=MeetingStatus.ACTIVE,
        action_items=[],
        metadata={"canonical_memory_item_id": "memory-3"},
    )
    task = Task(
        id="task-3",
        workspace_id=session.workspace_id,
        message_id="attempt-3",
        execution_id=None,
        pack_id="workspace.list_executions",
        task_type="tool_execution",
        status=TaskStatus.SUCCEEDED,
        params={},
        result={},
        execution_context={},
        meeting_session_id=session.id,
        completed_at=_utc_now(),
    )
    meeting_store = FakeMeetingSessionStore(session, [])
    service = MeetingTerminalEvidenceRefreshService(
        meeting_session_store=meeting_store,
        artifact_store=FakeArtifactStore(None),
        evidence_link_store=FakeEvidenceLinkStore(),
    )

    result = service.refresh_for_task(task)

    assert result == {"refreshed": False, "reason": "meeting_session_not_closed"}
    assert meeting_store.updated_session is None
