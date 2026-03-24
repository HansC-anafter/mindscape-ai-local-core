"""Unit tests for meeting memory writeback orchestration."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

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


class TestMeetingMemoryWritebackOrchestrator:
    def test_first_run_creates_digest_memory_item_and_evidence(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        orchestrator = MeetingMemoryWritebackOrchestrator(
            run_store=FakeRunStore(),
            digest_store=FakeDigestStore(),
            memory_item_store=FakeMemoryItemStore(),
            memory_version_store=FakeMemoryVersionStore(),
            evidence_link_store=FakeEvidenceLinkStore(),
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

    def test_completed_run_is_idempotent(self):
        adapter = FakeLegacyProjectionAdapter()
        metadata_adapter = FakeMetadataProjectionAdapter()
        run_store = FakeRunStore()
        digest_store = FakeDigestStore()
        item_store = FakeMemoryItemStore()
        version_store = FakeMemoryVersionStore()
        evidence_store = FakeEvidenceLinkStore()

        orchestrator = MeetingMemoryWritebackOrchestrator(
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
