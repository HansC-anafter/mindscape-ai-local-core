"""Tests for canonical-source linkage in legacy governance projection."""

import pytest

from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.services.personal_governance import digest_extraction as digest_module
from backend.app.services.personal_governance.digest_extraction import (
    DigestExtractionService,
)


class FakePersonalKnowledgeStore:
    def __init__(self):
        self.created = []

    def find_similar_content(self, owner_profile_id, content):
        return None

    def count_candidates_since(self, owner_profile_id, workspace_id, since):
        return 0

    def create(self, entry):
        self.created.append(entry)
        return entry


class FakeGoalLedgerStore:
    def __init__(self):
        self.created = []

    def list_by_owner(self, owner_profile_id, limit=50):
        return []

    def create(self, entry):
        self.created.append(entry)
        return entry


class FakeSessionDigestStore:
    pass


@pytest.mark.asyncio
async def test_extract_from_digest_attaches_canonical_projection_metadata(monkeypatch):
    async def fake_llm(system_prompt, user_prompt):
        return {
            "personal_knowledge": [
                {
                    "content": "The user prefers structured decision-making in ambiguous meetings.",
                    "knowledge_type": "pattern",
                    "confidence": 0.82,
                }
            ],
            "goals": [
                {
                    "title": "Turn meeting outcomes into a reusable operating cadence",
                    "description": "Stabilize the weekly reflection loop.",
                    "horizon": "quarterly",
                    "confidence": 0.88,
                }
            ],
        }

    monkeypatch.setattr(digest_module, "_call_extraction_llm", fake_llm)

    service = DigestExtractionService()
    service.pk_store = FakePersonalKnowledgeStore()
    service.gl_store = FakeGoalLedgerStore()
    service.digest_store = FakeSessionDigestStore()

    digest = SessionDigest(
        owner_profile_id="profile-001",
        source_type="meeting",
        source_id="meeting-001",
        workspace_refs=["ws-001"],
        summary_md="The team aligned on a more structured weekly review and rejected a looser cadence.",
    )

    result = await service.extract_from_digest(
        digest,
        meta_session_id="meeting-001",
        projection_context={
            "source_memory_item_id": "mem-123",
            "source_writeback_run_id": "run-456",
            "projection_stage": "legacy_governance_v1",
            "source_digest_id": digest.id,
        },
    )

    assert result["knowledge_created"] == 1
    assert result["goals_created"] == 1

    knowledge = service.pk_store.created[0]
    goal = service.gl_store.created[0]

    assert knowledge.metadata["canonical_projection"]["source_memory_item_id"] == "mem-123"
    assert knowledge.metadata["canonical_projection"]["source_writeback_run_id"] == "run-456"
    assert goal.metadata["canonical_projection"]["source_memory_item_id"] == "mem-123"
    assert goal.metadata["canonical_projection"]["source_writeback_run_id"] == "run-456"

    assert result["receipts"][0].metadata["canonical_projection"]["source_memory_item_id"] == "mem-123"
    assert result["receipts"][1].metadata["canonical_projection"]["source_writeback_run_id"] == "run-456"
