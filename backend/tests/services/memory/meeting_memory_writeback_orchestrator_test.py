"""Unit tests for meeting memory writeback orchestration."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.app.models.reasoning_trace import (
    ReasoningGraph,
    ReasoningNode,
    ReasoningTrace,
)
from backend.app.models.lens_patch import LensPatch, PatchStatus
from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.mindscape import IntentLog
from backend.app.models.personal_governance.writeback_receipt import WritebackReceipt
from backend.app.models.lens_receipt import LensReceipt
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType, Task, TaskStatus
from backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator import (
    MeetingMemoryWritebackOrchestrator,
)


def _utc_now():
    return datetime.now(timezone.utc)


@dataclass
class FakeSession:
    id: str = "sess-001"
    workspace_id: str = "ws-001"
    project_id: Optional[str] = "proj-001"
    started_at: datetime = field(default_factory=_utc_now)
    ended_at: datetime = field(default_factory=_utc_now)
    action_items: list = field(
        default_factory=lambda: [
            {"title": "Draft homepage copy", "description": "First pass"}
        ]
    )
    decisions: list = field(default_factory=lambda: ["approve_direction"])
    minutes_md: str = "We aligned on the direction and agreed on the next draft."


class FakeRunStore:
    def __init__(self):
        self.by_id = {}
        self.by_key = {}

    def get_or_create(self, **kwargs):
        existing = self.by_key.get(kwargs["idempotency_key"])
        if existing:
            return existing, False
        from backend.app.models.memory_contract import MemoryWritebackRun

        run = MemoryWritebackRun.new(
            run_type=kwargs["run_type"],
            source_scope=kwargs["source_scope"],
            source_id=kwargs["source_id"],
            idempotency_key=kwargs["idempotency_key"],
            metadata=kwargs.get("metadata"),
        )
        self.by_id[run.id] = run
        self.by_key[run.idempotency_key] = run
        return run, True

    def get(self, run_id):
        return self.by_id.get(run_id)

    def mark_stage(self, run_id, *, last_stage, summary_update=None):
        run = self.by_id[run_id]
        run.last_stage = last_stage
        run.summary.update(summary_update or {})
        return run

    def mark_completed(
        self, run_id, *, summary=None, update_mode_summary=None, last_stage="completed"
    ):
        run = self.by_id[run_id]
        run.status = "completed"
        run.last_stage = last_stage
        run.summary.update(summary or {})
        run.update_mode_summary.update(update_mode_summary or {})
        return run

    def mark_failed(self, run_id, *, error_detail, summary=None, last_stage="failed"):
        run = self.by_id[run_id]
        run.status = "failed"
        run.last_stage = last_stage
        run.error_detail = error_detail
        run.summary.update(summary or {})
        return run


class FakeDigestStore:
    def __init__(self):
        self.by_source = {}
        self.created = []

    def get_by_source(self, source_type, source_id):
        return self.by_source.get((source_type, source_id))

    def create(self, digest):
        self.by_source[(digest.source_type, digest.source_id)] = digest
        self.created.append(digest)
        return digest


class FakeMemoryItemStore:
    def __init__(self):
        self.by_subject = {}
        self.created = []

    def find_by_subject(
        self, *, kind, subject_type, subject_id, context_type="", context_id=""
    ):
        return self.by_subject.get(
            (kind, subject_type, subject_id, context_type, context_id)
        )

    def create(self, item):
        key = (
            item.kind,
            item.subject_type,
            item.subject_id,
            item.context_type,
            item.context_id,
        )
        self.by_subject[key] = item
        self.created.append(item)
        return item


class FakeMemoryVersionStore:
    def __init__(self):
        self.created = []

    def create(self, version):
        self.created.append(version)
        return version


class FakeEvidenceLinkStore:
    def __init__(self):
        self.links = []

    def exists(self, *, memory_item_id, evidence_type, evidence_id, link_role):
        return any(
            link.memory_item_id == memory_item_id
            and link.evidence_type == evidence_type
            and link.evidence_id == evidence_id
            and link.link_role == link_role
            for link in self.links
        )

    def create(self, link):
        self.links.append(link)
        return link


class FakeReasoningTraceStore:
    def __init__(self, traces=None):
        self.traces = list(traces or [])
        self.calls = []

    def get_by_session(self, meeting_session_id):
        self.calls.append(meeting_session_id)
        return [
            trace
            for trace in self.traces
            if trace.meeting_session_id == meeting_session_id
        ]


class FakeLensReceiptStore:
    def __init__(self, receipts_by_execution_id=None):
        self.receipts_by_execution_id = dict(receipts_by_execution_id or {})
        self.calls = []

    def get_by_execution_id(self, execution_id):
        self.calls.append(execution_id)
        return self.receipts_by_execution_id.get(execution_id)


class FakeLensPatchStore:
    def __init__(self, patches=None):
        self.patches = list(patches or [])
        self.calls = []

    def get_by_session(self, meeting_session_id):
        self.calls.append(meeting_session_id)
        return [
            patch
            for patch in self.patches
            if patch.meeting_session_id == meeting_session_id
        ]


class FakeTaskStore:
    def __init__(self, tasks_by_execution_id=None):
        self.tasks_by_execution_id = dict(tasks_by_execution_id or {})
        self.calls = []

    def get_task_by_execution_id(self, execution_id):
        self.calls.append(execution_id)
        return self.tasks_by_execution_id.get(execution_id)


class FakeArtifactStore:
    def __init__(self, artifacts_by_execution_id=None):
        self.artifacts_by_execution_id = dict(artifacts_by_execution_id or {})
        self.calls = []

    def get_by_execution_id(self, execution_id):
        self.calls.append(execution_id)
        return self.artifacts_by_execution_id.get(execution_id)


class FakeStageResultsStore:
    def __init__(self, results_by_execution_id=None):
        self.results_by_execution_id = dict(results_by_execution_id or {})
        self.calls = []

    def list_stage_results(self, execution_id=None, step_id=None, limit=100):
        self.calls.append(
            {
                "execution_id": execution_id,
                "step_id": step_id,
                "limit": limit,
            }
        )
        if execution_id:
            return list(self.results_by_execution_id.get(execution_id, []))
        return []


class FakeIntentLogStore:
    def __init__(self, logs=None):
        self.logs = list(logs or [])
        self.calls = []

    def list_intent_logs(
        self,
        profile_id=None,
        workspace_id=None,
        project_id=None,
        start_time=None,
        end_time=None,
        has_override=None,
        limit=100,
    ):
        self.calls.append(
            {
                "profile_id": profile_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "start_time": start_time,
                "end_time": end_time,
                "has_override": has_override,
                "limit": limit,
            }
        )
        results = [
            log
            for log in self.logs
            if (workspace_id is None or log.workspace_id == workspace_id)
            and (project_id is None or log.project_id == project_id)
        ]
        if start_time is not None:
            results = [log for log in results if log.timestamp >= start_time]
        if end_time is not None:
            results = [log for log in results if log.timestamp <= end_time]
        return results[:limit]


class FakeGovernanceStore:
    def __init__(self, decisions_by_execution_id=None):
        self.decisions_by_execution_id = dict(decisions_by_execution_id or {})
        self.calls = []

    def list_decisions_for_execution(self, *, workspace_id, execution_id, limit=50):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "execution_id": execution_id,
                "limit": limit,
            }
        )
        return list(self.decisions_by_execution_id.get(execution_id, []))


class FakeMeetingSessionStore:
    def __init__(self, decisions=None):
        self.decisions = list(decisions or [])
        self.calls = []

    def list_decisions_by_session(self, session_id):
        self.calls.append(session_id)
        return [decision for decision in self.decisions if decision.session_id == session_id]


class FakeWritebackReceiptStore:
    def __init__(self, receipts=None, resolver=None):
        self.receipts = list(receipts or [])
        self.calls = []
        self.resolver = resolver

    def list_by_canonical_memory_item(self, source_memory_item_id, limit=50):
        self.calls.append((source_memory_item_id, limit))
        if self.resolver is not None:
            return list(self.resolver(source_memory_item_id))
        return [
            receipt
            for receipt in self.receipts
            if (receipt.metadata.get("canonical_projection", {}) or {}).get("source_memory_item_id")
            == source_memory_item_id
        ]


class FakeLegacyProjectionAdapter:
    def __init__(self):
        self.calls = []

    def dispatch_digest_projection(
        self,
        digest,
        meta_session_id,
        *,
        source_memory_item_id,
        source_writeback_run_id,
        projection_stage="legacy_governance_v1",
    ):
        self.calls.append(
            {
                "digest_id": digest.id,
                "meta_session_id": meta_session_id,
                "source_memory_item_id": source_memory_item_id,
                "source_writeback_run_id": source_writeback_run_id,
                "projection_stage": projection_stage,
            }
        )


class FakeMetadataProjectionAdapter:
    def __init__(self):
        self.calls = []

    def dispatch_digest_projection(
        self,
        digest,
        *,
        source_memory_item_id,
        source_writeback_run_id,
        projection_stage="legacy_metadata_memory_v1",
    ):
        self.calls.append(
            {
                "digest_id": digest.id,
                "source_memory_item_id": source_memory_item_id,
                "source_writeback_run_id": source_writeback_run_id,
                "projection_stage": projection_stage,
            }
        )


def build_orchestrator(**overrides):
    defaults = {
        "run_store": FakeRunStore(),
        "digest_store": FakeDigestStore(),
        "memory_item_store": FakeMemoryItemStore(),
        "memory_version_store": FakeMemoryVersionStore(),
        "evidence_link_store": FakeEvidenceLinkStore(),
        "meeting_session_store": FakeMeetingSessionStore(),
        "reasoning_trace_store": FakeReasoningTraceStore(),
        "writeback_receipt_store": FakeWritebackReceiptStore(),
        "lens_receipt_store": FakeLensReceiptStore(),
        "lens_patch_store": FakeLensPatchStore(),
        "task_store": FakeTaskStore(),
        "artifact_store": FakeArtifactStore(),
        "stage_results_store": FakeStageResultsStore(),
        "intent_log_store": FakeIntentLogStore(),
        "governance_store": FakeGovernanceStore(),
        "legacy_projection_adapter": FakeLegacyProjectionAdapter(),
        "metadata_projection_adapter": FakeMetadataProjectionAdapter(),
    }
    defaults.update(overrides)
    return MeetingMemoryWritebackOrchestrator(**defaults)


class TestMeetingMemoryWritebackOrchestrator:
    def test_first_run_creates_digest_memory_item_and_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["created"] is True
        assert result["digest"] is not None
        assert result["memory_item"] is not None
        assert result["run"].status == "completed"
        assert result["run"].summary["legacy_extraction_triggered"] is True
        assert result["run"].summary["legacy_metadata_projection_triggered"] is True
        assert len(adapter.calls) == 1
        assert len(metadata_adapter.calls) == 1
        assert adapter.calls[0]["source_memory_item_id"] == result["memory_item"].id
        assert adapter.calls[0]["source_writeback_run_id"] == result["run"].id
        assert (
            metadata_adapter.calls[0]["source_memory_item_id"]
            == result["memory_item"].id
        )
        assert (
            metadata_adapter.calls[0]["source_writeback_run_id"] == result["run"].id
        )
        assert result["run"].summary["reasoning_trace_count"] == 0
        assert result["run"].summary["reasoning_trace_links_created"] == 0
        assert result["run"].summary["lens_receipt_count"] == 0
        assert result["run"].summary["lens_receipt_links_created"] == 0
        assert result["run"].summary["meeting_decision_count"] == 0
        assert result["run"].summary["meeting_decision_links_created"] == 0
        assert result["run"].summary["task_execution_count"] == 0
        assert result["run"].summary["task_execution_links_created"] == 0
        assert result["run"].summary["execution_trace_count"] == 0
        assert result["run"].summary["execution_trace_links_created"] == 0
        assert result["run"].summary["artifact_result_count"] == 0
        assert result["run"].summary["artifact_result_links_created"] == 0
        assert result["run"].summary["stage_result_count"] == 0
        assert result["run"].summary["stage_result_links_created"] == 0
        assert result["run"].summary["intent_log_count"] == 0
        assert result["run"].summary["intent_log_links_created"] == 0
        assert result["run"].summary["governance_decision_count"] == 0
        assert result["run"].summary["governance_decision_links_created"] == 0
        assert result["run"].summary["lens_patch_count"] == 0
        assert result["run"].summary["lens_patch_links_created"] == 0
        assert result["run"].summary["writeback_receipt_count"] == 0
        assert result["run"].summary["writeback_receipt_links_created"] == 0

    def test_completed_run_is_idempotent(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        run_store = FakeRunStore()
        digest_store = FakeDigestStore()
        item_store = FakeMemoryItemStore()
        version_store = FakeMemoryVersionStore()
        evidence_store = FakeEvidenceLinkStore()

        orchestrator = build_orchestrator(
            run_store=run_store,
            digest_store=digest_store,
            memory_item_store=item_store,
            memory_version_store=version_store,
            evidence_link_store=evidence_store,
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        first = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )
        second = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert first["run"].id == second["run"].id
        assert len(digest_store.created) == 1
        assert len(item_store.created) == 1
        assert len(version_store.created) == 1
        assert len(evidence_store.links) == 1
        assert len(adapter.calls) == 1
        assert len(metadata_adapter.calls) == 1
        assert second["created"] is False

    def test_first_run_attaches_reasoning_trace_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        trace = ReasoningTrace.new(
            workspace_id="ws-001",
            graph=ReasoningGraph(
                nodes=[
                    ReasoningNode(
                        id="n1",
                        content="The draft should keep direct tradeoff framing.",
                        type="conclusion",
                    )
                ],
                edges=[],
                answer="Keep the architectural tradeoff framing explicit.",
            ),
            meeting_session_id="sess-001",
            execution_id="exec-001",
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            reasoning_trace_store=FakeReasoningTraceStore([trace]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["reasoning_trace_count"] == 1
        assert result["run"].summary["reasoning_trace_links_created"] == 1
        assert len(evidence_store.links) == 2
        reasoning_links = [
            link for link in evidence_store.links if link.evidence_type == "reasoning_trace"
        ]
        assert len(reasoning_links) == 1
        assert reasoning_links[0].evidence_id == trace.id
        assert reasoning_links[0].link_role == "supports"
        assert reasoning_links[0].metadata["execution_id"] == "exec-001"
        assert reasoning_links[0].excerpt == "Keep the architectural tradeoff framing explicit."

    def test_first_run_attaches_lens_receipt_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        trace = ReasoningTrace.new(
            workspace_id="ws-001",
            graph=ReasoningGraph(
                nodes=[
                    ReasoningNode(
                        id="n1",
                        content="Keep the tone deliberate.",
                        type="conclusion",
                    )
                ],
                edges=[],
            ),
            meeting_session_id="sess-001",
            execution_id="exec-001",
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            reasoning_trace_store=FakeReasoningTraceStore([trace]),
            lens_receipt_store=FakeLensReceiptStore(
                {
                    "exec-001": LensReceipt(
                        id="lens-receipt-001",
                        execution_id="exec-001",
                        workspace_id="ws-001",
                        effective_lens_hash="lens-hash-001",
                        diff_summary="The lens tightened tone and kept the answer concise.",
                    )
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["lens_receipt_count"] == 1
        assert result["run"].summary["lens_receipt_links_created"] == 1
        lens_links = [
            link for link in evidence_store.links if link.evidence_type == "lens_receipt"
        ]
        assert len(lens_links) == 1
        assert lens_links[0].evidence_id == "lens-receipt-001"
        assert lens_links[0].metadata["execution_id"] == "exec-001"
        assert (
            lens_links[0].excerpt
            == "The lens tightened tone and kept the answer concise."
        )

    def test_first_run_attaches_meeting_decision_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-001",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Ship the canonical memory writeback before broader retrieval work.",
            status="pending",
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["meeting_decision_count"] == 1
        assert result["run"].summary["meeting_decision_links_created"] == 1
        decision_links = [
            link for link in evidence_store.links if link.evidence_type == "meeting_decision"
        ]
        assert len(decision_links) == 1
        assert decision_links[0].evidence_id == "decision-001"
        assert decision_links[0].metadata["category"] == "action"
        assert (
            decision_links[0].excerpt
            == "Ship the canonical memory writeback before broader retrieval work."
        )

    def test_first_run_attaches_task_execution_evidence_from_meeting_decision(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Run the outline generation task and review the result.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            task_store=FakeTaskStore(
                {
                    "exec-001": Task(
                        id="task-001",
                        workspace_id="ws-001",
                        message_id="msg-001",
                        execution_id="exec-001",
                        pack_id="outline_pack",
                        task_type="generate_outline",
                        status=TaskStatus.SUCCEEDED,
                        result={"summary": "Generated a first-pass outline with three sections."},
                    )
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["task_execution_count"] == 1
        assert result["run"].summary["task_execution_links_created"] == 1
        task_links = [
            link for link in evidence_store.links if link.evidence_type == "task_execution"
        ]
        assert len(task_links) == 1
        assert task_links[0].evidence_id == "exec-001"
        assert task_links[0].metadata["task_id"] == "task-001"
        assert task_links[0].metadata["pack_id"] == "outline_pack"
        assert (
            task_links[0].excerpt
            == "Generated a first-pass outline with three sections."
        )

    def test_first_run_attaches_execution_trace_evidence_from_task_result(self, tmp_path):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002a",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Run the external runtime task and capture its trace.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        trace_dir = tmp_path / ".mindscape" / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / "trace-exec-001.json"
        trace_file.write_text(
            json.dumps(
                {
                    "execution_id": "trace-exec-001",
                    "agent_type": "openclaw",
                    "task_description": "Generate a concise landing-page outline.",
                    "output_summary": "Produced a concise landing-page outline and updated the draft files.",
                    "success": True,
                    "duration_seconds": 12.5,
                    "tool_calls": [
                        {"tool_name": "file_read"},
                        {"tool_name": "file_write"},
                    ],
                    "file_changes": [
                        {"path": "draft.md", "change_type": "created"},
                        {"path": "notes.md", "change_type": "modified"},
                    ],
                    "sandbox_path": str(tmp_path),
                }
            ),
            encoding="utf-8",
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            task_store=FakeTaskStore(
                {
                    "exec-001": Task(
                        id="task-001a",
                        workspace_id="ws-001",
                        message_id="msg-001a",
                        execution_id="exec-001",
                        pack_id="external_runtime_pack",
                        task_type="workspace_agent_execute",
                        status=TaskStatus.SUCCEEDED,
                        result={
                            "execution_trace": {
                                "execution_id": "trace-exec-001",
                                "trace_id": "trace-001",
                                "agent": "openclaw",
                                "tool_calls": ["file_read", "file_write"],
                                "files_created": ["draft.md"],
                                "files_modified": ["notes.md"],
                                "sandbox_path": str(tmp_path),
                            }
                        },
                    )
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["execution_trace_count"] == 1
        assert result["run"].summary["execution_trace_links_created"] == 1
        execution_trace_links = [
            link for link in evidence_store.links if link.evidence_type == "execution_trace"
        ]
        assert len(execution_trace_links) == 1
        assert execution_trace_links[0].evidence_id == "trace-exec-001"
        assert execution_trace_links[0].metadata["agent"] == "openclaw"
        assert execution_trace_links[0].metadata["tool_call_count"] == 2
        assert execution_trace_links[0].metadata["files_created_count"] == 1
        assert execution_trace_links[0].metadata["files_modified_count"] == 1
        assert execution_trace_links[0].metadata["file_change_count"] == 2
        assert execution_trace_links[0].metadata["task_description"] == "Generate a concise landing-page outline."
        assert (
            execution_trace_links[0].metadata["output_summary"]
            == "Produced a concise landing-page outline and updated the draft files."
        )
        assert execution_trace_links[0].metadata["trace_source"] == "trace_file"
        assert (
            execution_trace_links[0].metadata["trace_file_path"]
            == str(trace_dir / "trace-exec-001.json")
        )
        assert execution_trace_links[0].metadata["sandbox_path"] == str(tmp_path)
        assert (
            execution_trace_links[0].excerpt
            == "Produced a concise landing-page outline and updated the draft files."
        )

    def test_first_run_attaches_stage_result_evidence_from_meeting_decision(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002b",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Run the outline generation task and review the draft stage.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        from backend.app.services.stores.stage_results_store import StageResult

        stage_result = StageResult(
            id="stage-001",
            execution_id="exec-001",
            step_id="step-001",
            stage_name="final_output",
            result_type="draft",
            content={"summary": "Produced a structured outline draft."},
            preview="Produced a structured outline draft.",
            requires_review=True,
            review_status="pending",
            artifact_id="artifact-001",
            created_at=_utc_now(),
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            stage_results_store=FakeStageResultsStore({"exec-001": [stage_result]}),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["stage_result_count"] == 1
        assert result["run"].summary["stage_result_links_created"] == 1
        stage_links = [
            link for link in evidence_store.links if link.evidence_type == "stage_result"
        ]
        assert len(stage_links) == 1
        assert stage_links[0].evidence_id == "stage-001"
        assert stage_links[0].metadata["execution_id"] == "exec-001"
        assert stage_links[0].metadata["stage_name"] == "final_output"
        assert stage_links[0].metadata["review_status"] == "pending"
        assert stage_links[0].excerpt == "Produced a structured outline draft."

    def test_first_run_attaches_intent_log_evidence_for_session_window(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        session = FakeSession()
        intent_log = IntentLog(
            id="intent-log-001",
            timestamp=session.ended_at,
            raw_input="Help me draft the outline for the landing page.",
            channel="api",
            profile_id="profile-001",
            project_id="proj-001",
            workspace_id="ws-001",
            pipeline_steps={},
            final_decision={
                "selected_playbook_code": "outline_pack",
                "resolution_strategy": "direct_match",
                "requires_user_approval": True,
            },
            user_override={"selected_playbook_code": "outline_pack"},
            metadata={},
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            intent_log_store=FakeIntentLogStore([intent_log]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=session,
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["intent_log_count"] == 1
        assert result["run"].summary["intent_log_links_created"] == 1
        intent_links = [
            link for link in evidence_store.links if link.evidence_type == "intent_log"
        ]
        assert len(intent_links) == 1
        assert intent_links[0].evidence_id == "intent-log-001"
        assert intent_links[0].metadata["selected_playbook_code"] == "outline_pack"
        assert intent_links[0].metadata["requires_user_approval"] is True
        assert intent_links[0].metadata["has_user_override"] is True
        assert (
            intent_links[0].excerpt
            == "Selected outline_pack. Resolution direct_match. User approval required. User override recorded."
        )

    def test_first_run_attaches_governance_decision_evidence_from_execution(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-002c",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Review whether the generated outline can be approved.",
            status="dispatched",
            source_action_item={"execution_id": "exec-001"},
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            governance_store=FakeGovernanceStore(
                {
                    "exec-001": [
                        {
                            "decision_id": "gov-001",
                            "workspace_id": "ws-001",
                            "execution_id": "exec-001",
                            "timestamp": _utc_now().isoformat(),
                            "layer": "policy",
                            "approved": True,
                            "reason": "The draft satisfied workspace guardrails.",
                            "playbook_code": "outline_pack",
                            "metadata": {"requires_review": False},
                        }
                    ]
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["governance_decision_count"] == 1
        assert result["run"].summary["governance_decision_links_created"] == 1
        governance_links = [
            link
            for link in evidence_store.links
            if link.evidence_type == "governance_decision"
        ]
        assert len(governance_links) == 1
        assert governance_links[0].evidence_id == "gov-001"
        assert governance_links[0].metadata["execution_id"] == "exec-001"
        assert governance_links[0].metadata["layer"] == "policy"
        assert governance_links[0].metadata["approved"] is True
        assert (
            governance_links[0].excerpt
            == "Policy approval=True. Playbook outline_pack. The draft satisfied workspace guardrails."
        )

    def test_first_run_attaches_lens_patch_evidence_for_session(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        patch = LensPatch(
            id="lens-patch-001",
            lens_id="lens-001",
            meeting_session_id="sess-001",
            delta={
                "voice.tone": {"before": "neutral", "after": "deliberate"},
                "strategy.mode": {"before": "broad", "after": "focused"},
            },
            evidence_refs=["trace-001", "decision-001"],
            confidence=0.84,
            status=PatchStatus.APPROVED,
            lens_version_before=3,
            lens_version_after=4,
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            lens_patch_store=FakeLensPatchStore([patch]),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["lens_patch_count"] == 1
        assert result["run"].summary["lens_patch_links_created"] == 1
        lens_patch_links = [
            link for link in evidence_store.links if link.evidence_type == "lens_patch"
        ]
        assert len(lens_patch_links) == 1
        assert lens_patch_links[0].evidence_id == "lens-patch-001"
        assert lens_patch_links[0].metadata["lens_id"] == "lens-001"
        assert lens_patch_links[0].metadata["status"] == "approved"
        assert lens_patch_links[0].metadata["delta_magnitude"] == 2
        assert lens_patch_links[0].metadata["evidence_ref_count"] == 2
        assert (
            lens_patch_links[0].excerpt
            == "Lens patch approved. Changed voice.tone, strategy.mode. Confidence 0.84."
        )

    def test_first_run_attaches_artifact_result_evidence_from_meeting_decision(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        decision = MeetingDecision(
            id="decision-003",
            session_id="sess-001",
            workspace_id="ws-001",
            category="action",
            content="Review the generated artifact from the execution.",
            status="dispatched",
            source_action_item={"execution_id": "exec-002"},
        )
        evidence_store = FakeEvidenceLinkStore()
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            meeting_session_store=FakeMeetingSessionStore([decision]),
            artifact_store=FakeArtifactStore(
                {
                    "exec-002": Artifact(
                        id="artifact-001",
                        workspace_id="ws-001",
                        task_id="task-002",
                        execution_id="exec-002",
                        playbook_code="outline_pack",
                        artifact_type=ArtifactType.DRAFT,
                        title="Outline Draft",
                        summary="Generated an outline artifact with introduction, argument, and closing sections.",
                        primary_action_type=PrimaryActionType.PREVIEW,
                        metadata={
                            "landing": {
                                "artifact_dir": "/tmp/ws-001/artifacts/exec-002",
                                "result_json_path": "/tmp/ws-001/artifacts/exec-002/result.json",
                                "summary_md_path": "/tmp/ws-001/artifacts/exec-002/summary.md",
                                "attachments_count": 2,
                                "attachments": [
                                    "/tmp/ws-001/artifacts/exec-002/attachments/draft.md",
                                    "/tmp/ws-001/artifacts/exec-002/attachments/notes.md",
                                ],
                                "landed_at": "2026-03-25T00:00:00Z",
                            }
                        },
                    )
                }
            ),
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        assert result["run"].summary["artifact_result_count"] == 1
        assert result["run"].summary["artifact_result_links_created"] == 1
        artifact_links = [
            link for link in evidence_store.links if link.evidence_type == "artifact_result"
        ]
        assert len(artifact_links) == 1
        assert artifact_links[0].evidence_id == "artifact-001"
        assert artifact_links[0].metadata["execution_id"] == "exec-002"
        assert artifact_links[0].metadata["playbook_code"] == "outline_pack"
        assert (
            artifact_links[0].metadata["landing_artifact_dir"]
            == "/tmp/ws-001/artifacts/exec-002"
        )
        assert (
            artifact_links[0].metadata["landing_result_json_path"]
            == "/tmp/ws-001/artifacts/exec-002/result.json"
        )
        assert artifact_links[0].metadata["landing_attachments_count"] == 2
        assert artifact_links[0].metadata["landing_attachments"] == [
            "/tmp/ws-001/artifacts/exec-002/attachments/draft.md",
            "/tmp/ws-001/artifacts/exec-002/attachments/notes.md",
        ]
        assert artifact_links[0].metadata["landing_landed_at"] == "2026-03-25T00:00:00Z"
        assert (
            artifact_links[0].excerpt
            == "Generated an outline artifact with introduction, argument, and closing sections."
        )

    def test_first_run_attaches_writeback_receipt_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        evidence_store = FakeEvidenceLinkStore()
        receipt_store = FakeWritebackReceiptStore(
            resolver=lambda source_memory_item_id: [
                WritebackReceipt(
                    id="receipt-001",
                    meta_session_id="sess-001",
                    source_decision_id="digest-001",
                    target_table="personal_knowledge",
                    target_id="pk-001",
                    writeback_type="candidate",
                    status="completed",
                    metadata={
                        "canonical_projection": {
                            "source_memory_item_id": source_memory_item_id,
                        }
                    },
                )
            ]
        )
        orchestrator = build_orchestrator(
            evidence_link_store=evidence_store,
            writeback_receipt_store=receipt_store,
            legacy_projection_adapter=adapter,
            metadata_projection_adapter=metadata_adapter,
        )

        result = orchestrator.run_for_closed_session(
            session=FakeSession(),
            workspace=object(),
            profile_id="profile-001",
        )

        receipt_links = [
            link
            for link in evidence_store.links
            if link.evidence_type == "writeback_receipt"
        ]
        assert result["run"].summary["writeback_receipt_count"] == 1
        assert result["run"].summary["writeback_receipt_links_created"] == 1
        assert len(receipt_links) == 1
        assert receipt_links[0].evidence_id == "receipt-001"
        assert receipt_links[0].link_role == "derived_from"
        assert receipt_links[0].metadata["target_table"] == "personal_knowledge"
