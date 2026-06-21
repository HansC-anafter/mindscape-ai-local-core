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
