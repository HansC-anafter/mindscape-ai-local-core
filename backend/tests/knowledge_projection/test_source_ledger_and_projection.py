import hashlib
from datetime import datetime, timezone

import pytest

from backend.app.services.knowledge_projection.contracts import (
    KnowledgeProjectionEntry,
    KnowledgeProjectionRequest,
    KnowledgeSourceIntake,
    KnowledgeSourceIntakeReceipt,
)
from backend.app.services.knowledge_projection.projection import (
    KnowledgeProjectionService,
)
from backend.app.services.knowledge_projection.source_ledger import (
    KnowledgeSourceLedgerFacade,
    KnowledgeSourcePayloadError,
)


class _SourceRepository:
    def __init__(self):
        self.calls = []

    def record_intake(self, intake, *, intake_id):
        self.calls.append((intake, intake_id))
        return KnowledgeSourceIntakeReceipt(
            intake_id=intake_id,
            source_instance_id=intake.source_instance_id,
            source_revision=intake.source_revision,
            content_hash=intake.content_hash,
            created=True,
        )


class _ProjectionRepository:
    def __init__(self):
        self.rows = {}

    def get_or_create_manifest(self, **kwargs):
        key = kwargs["input_revision_hash"]
        if key in self.rows:
            return self.rows[key], False
        row = {
            "id": kwargs["projection_id"],
            "content_hash": kwargs["content_hash"],
            "artifact_ref": kwargs["request"].artifact_ref,
        }
        self.rows[key] = row
        return row, True


def _intake(**overrides):
    payload = {
        "source_instance_id": "source:docs:1",
        "owner_type": "capability",
        "owner_id": "adaptive_learning",
        "source_revision": "rev-1",
        "content_hash": hashlib.sha256(b"source").hexdigest(),
        "evidence_type": "artifact",
        "evidence_id": "artifact-1",
        "checkpoint": {"page": 2},
    }
    payload.update(overrides)
    return KnowledgeSourceIntake(**payload)


def test_source_ledger_uses_stable_intake_identity_and_rejects_secrets():
    repository = _SourceRepository()
    facade = KnowledgeSourceLedgerFacade(repository=repository)

    first = facade.record_intake(_intake())
    second = facade.record_intake(_intake())

    assert first.intake_id == second.intake_id
    assert len(repository.calls) == 2
    with pytest.raises(KnowledgeSourcePayloadError, match="secret-like"):
        facade.record_intake(_intake(metadata={"refresh_token": "must-not-land"}))


def test_projection_is_deterministic_and_markdown_is_not_an_input():
    repository = _ProjectionRepository()
    service = KnowledgeProjectionService(repository=repository)
    entries = [
        KnowledgeProjectionEntry(
            memory_version_id="mv-b",
            stable_subject_key="subject:b",
            title="B",
            claim="Claim B",
            lifecycle_status="active",
            verification_status="verified",
            confidence=0.9,
            evidence_refs=["ev-2", "ev-1"],
        ),
        KnowledgeProjectionEntry(
            memory_version_id="mv-a",
            stable_subject_key="subject:a",
            title="A",
            claim="Claim A",
            lifecycle_status="candidate",
            verification_status="observed",
            confidence=0.7,
            evidence_refs=["ev-1"],
        ),
    ]
    request = KnowledgeProjectionRequest(
        projection_type="group_brain",
        scope_type="group",
        scope_id="group-1",
        topology_snapshot_id="snapshot-1",
        policy_revision="policy-v1",
        generator_revision="generator-v1",
        logical_generated_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        artifact_ref="artifact://group-1.md",
        entries=entries,
    )

    first = service.project(request)
    rebuilt = service.project(request.model_copy(update={"entries": list(reversed(entries))}))

    assert first.content_hash == rebuilt.content_hash
    assert first.markdown == rebuilt.markdown
    assert first.created is True
    assert rebuilt.created is False
    assert first.markdown.index("## A") < first.markdown.index("## B")
    locally_edited = first.markdown + "manual edit\n"
    assert locally_edited != service.project(request).markdown
