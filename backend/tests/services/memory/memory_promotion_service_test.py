from dataclasses import dataclass
from datetime import datetime, timezone

from backend.app.models.memory_contract import (
    MemoryEdgeType,
    MemoryItem,
    MemoryLifecycleStatus,
    MemoryVerificationStatus,
)
from backend.app.models.personal_governance.goal_ledger import GoalLedgerEntry
from backend.app.models.personal_governance.personal_knowledge import PersonalKnowledge
from backend.app.services.memory.promotion_service import MemoryPromotionService


def _utc_now():
    return datetime.now(timezone.utc)


class FakeRunStore:
    def __init__(self):
        self.by_key = {}
        self.by_id = {}

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
        self.by_key[run.idempotency_key] = run
        self.by_id[run.id] = run
        return run, True

    def mark_completed(self, run_id, *, summary=None, update_mode_summary=None, last_stage="completed"):
        run = self.by_id[run_id]
        run.status = "completed"
        run.summary.update(summary or {})
        run.update_mode_summary.update(update_mode_summary or {})
        run.last_stage = last_stage
        return run

    def mark_failed(self, run_id, *, error_detail, summary=None, last_stage="failed"):
        run = self.by_id[run_id]
        run.status = "failed"
        run.error_detail = error_detail
        run.summary.update(summary or {})
        run.last_stage = last_stage
        return run


class FakeMemoryItemStore:
    def __init__(self, items):
        self.items = {item.id: item for item in items}
        self.created = []

    def get(self, item_id):
        return self.items.get(item_id)

    def update(self, item):
        self.items[item.id] = item
        return item

    def create(self, item):
        self.items[item.id] = item
        self.created.append(item)
        return item


class FakeMemoryVersionStore:
    def __init__(self):
        self.created = []
        self.next_version_by_item = {}

    def get_next_version_no(self, memory_item_id):
        next_no = self.next_version_by_item.get(memory_item_id, 1)
        self.next_version_by_item[memory_item_id] = next_no + 1
        return next_no

    def create(self, version):
        self.created.append(version)
        self.next_version_by_item[version.memory_item_id] = version.version_no + 1
        return version


class FakeMemoryEdgeStore:
    def __init__(self):
        self.edges = []

    def exists(self, *, from_memory_id, to_memory_id, edge_type):
        return any(
            edge.from_memory_id == from_memory_id
            and edge.to_memory_id == to_memory_id
            and edge.edge_type == edge_type
            for edge in self.edges
        )

    def create(self, edge):
        self.edges.append(edge)
        return edge


class FakePersonalKnowledgeStore:
    def __init__(self, entries):
        self.entries = {entry.id: entry for entry in entries}

    def get(self, entry_id):
        return self.entries.get(entry_id)

    def list_by_canonical_memory_item(self, source_memory_item_id):
        return [
            entry
            for entry in self.entries.values()
            if (entry.metadata or {}).get("canonical_projection", {}).get(
                "source_memory_item_id"
            )
            == source_memory_item_id
        ]

    def update(self, entry):
        self.entries[entry.id] = entry
        return True


class FakeGoalLedgerStore:
    def __init__(self, entries):
        self.entries = {entry.id: entry for entry in entries}

    def get(self, entry_id):
        return self.entries.get(entry_id)

    def list_by_canonical_memory_item(self, source_memory_item_id):
        return [
            entry
            for entry in self.entries.values()
            if (entry.metadata or {}).get("canonical_projection", {}).get(
                "source_memory_item_id"
            )
            == source_memory_item_id
        ]

    def update(self, entry):
        self.entries[entry.id] = entry
        return True


def test_verify_candidate_promotes_memory_and_related_surfaces():
    item = MemoryItem(
        id="mem-1",
        title="Episode",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status=MemoryLifecycleStatus.CANDIDATE.value,
        verification_status=MemoryVerificationStatus.OBSERVED.value,
        observed_at=_utc_now(),
    )
    knowledge = PersonalKnowledge(id="pk-1", status="candidate")
    goal = GoalLedgerEntry(id="goal-1", status="pending_confirmation")

    service = MemoryPromotionService(
        run_store=FakeRunStore(),
        memory_item_store=FakeMemoryItemStore([item]),
        memory_version_store=FakeMemoryVersionStore(),
        memory_edge_store=FakeMemoryEdgeStore(),
        personal_knowledge_store=FakePersonalKnowledgeStore([knowledge]),
        goal_ledger_store=FakeGoalLedgerStore([goal]),
    )

    result = service.verify_candidate(
        "mem-1",
        related_knowledge_ids=["pk-1"],
        related_goal_ids=["goal-1"],
        reason="user confirmed",
    )

    assert result["memory_item"].lifecycle_status == MemoryLifecycleStatus.ACTIVE.value
    assert result["memory_item"].verification_status == MemoryVerificationStatus.VERIFIED.value
    assert service.personal_knowledge_store.get("pk-1").status == "verified"
    assert service.goal_ledger_store.get("goal-1").status == "active"
    assert result["run"].summary["transition"] == "verify"


def test_mark_stale_marks_memory_and_related_surfaces_stale():
    item = MemoryItem(
        id="mem-1",
        title="Episode",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status=MemoryLifecycleStatus.ACTIVE.value,
        verification_status=MemoryVerificationStatus.VERIFIED.value,
        observed_at=_utc_now(),
    )
    knowledge = PersonalKnowledge(id="pk-1", status="verified")
    goal = GoalLedgerEntry(id="goal-1", status="active")

    service = MemoryPromotionService(
        run_store=FakeRunStore(),
        memory_item_store=FakeMemoryItemStore([item]),
        memory_version_store=FakeMemoryVersionStore(),
        memory_edge_store=FakeMemoryEdgeStore(),
        personal_knowledge_store=FakePersonalKnowledgeStore([knowledge]),
        goal_ledger_store=FakeGoalLedgerStore([goal]),
    )

    result = service.mark_stale(
        "mem-1",
        related_knowledge_ids=["pk-1"],
        related_goal_ids=["goal-1"],
        reason="not reaffirmed",
    )

    assert result["memory_item"].lifecycle_status == MemoryLifecycleStatus.STALE.value
    assert service.personal_knowledge_store.get("pk-1").status == "stale"
    assert service.goal_ledger_store.get("goal-1").status == "stale"


def test_supersede_memory_creates_successor_and_edge():
    item = MemoryItem(
        id="mem-1",
        title="Old",
        claim="Old claim",
        summary="Old summary",
        lifecycle_status=MemoryLifecycleStatus.ACTIVE.value,
        verification_status=MemoryVerificationStatus.VERIFIED.value,
        observed_at=_utc_now(),
    )
    knowledge = PersonalKnowledge(id="pk-1", status="verified")
    goal = GoalLedgerEntry(id="goal-1", status="active")
    edge_store = FakeMemoryEdgeStore()
    item_store = FakeMemoryItemStore([item])

    service = MemoryPromotionService(
        run_store=FakeRunStore(),
        memory_item_store=item_store,
        memory_version_store=FakeMemoryVersionStore(),
        memory_edge_store=edge_store,
        personal_knowledge_store=FakePersonalKnowledgeStore([knowledge]),
        goal_ledger_store=FakeGoalLedgerStore([goal]),
    )

    result = service.supersede_memory(
        "mem-1",
        successor_title="New",
        successor_claim="New claim",
        successor_summary="New summary",
        related_knowledge_ids=["pk-1"],
        related_goal_ids=["goal-1"],
        reason="stronger evidence",
    )

    successor = result["successor_memory_item"]
    assert result["memory_item"].lifecycle_status == MemoryLifecycleStatus.SUPERSEDED.value
    assert successor.supersedes_memory_id == "mem-1"
    assert successor.lifecycle_status == MemoryLifecycleStatus.ACTIVE.value
    assert edge_store.edges[0].edge_type == MemoryEdgeType.SUPERSEDES.value
    assert service.personal_knowledge_store.get("pk-1").status == "deprecated"
    assert service.goal_ledger_store.get("goal-1").status == "deprecated"


def test_verify_candidate_auto_resolves_projected_legacy_rows():
    item = MemoryItem(
        id="mem-1",
        title="Episode",
        claim="Initial claim",
        summary="Initial summary",
        lifecycle_status=MemoryLifecycleStatus.CANDIDATE.value,
        verification_status=MemoryVerificationStatus.OBSERVED.value,
        observed_at=_utc_now(),
    )
    knowledge = PersonalKnowledge(
        id="pk-1",
        status="candidate",
        metadata={
            "canonical_projection": {
                "source_memory_item_id": "mem-1",
            }
        },
    )
    goal = GoalLedgerEntry(
        id="goal-1",
        status="pending_confirmation",
        metadata={
            "canonical_projection": {
                "source_memory_item_id": "mem-1",
            }
        },
    )

    service = MemoryPromotionService(
        run_store=FakeRunStore(),
        memory_item_store=FakeMemoryItemStore([item]),
        memory_version_store=FakeMemoryVersionStore(),
        memory_edge_store=FakeMemoryEdgeStore(),
        personal_knowledge_store=FakePersonalKnowledgeStore([knowledge]),
        goal_ledger_store=FakeGoalLedgerStore([goal]),
    )

    result = service.verify_candidate("mem-1", reason="auto resolved projection")

    assert result["memory_item"].lifecycle_status == MemoryLifecycleStatus.ACTIVE.value
    assert service.personal_knowledge_store.get("pk-1").status == "verified"
    assert service.goal_ledger_store.get("goal-1").status == "active"
    assert result["run"].summary["related_knowledge_count"] == 1
    assert result["run"].summary["related_goal_count"] == 1
