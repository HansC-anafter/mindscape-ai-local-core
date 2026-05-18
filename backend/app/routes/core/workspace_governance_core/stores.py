import asyncio

from fastapi import HTTPException

from backend.app.services.governance.governance_store import GovernanceStore
from backend.app.services.governance.memory_impact_graph_read_model import (
    MemoryImpactGraphReadModel,
)


def _get_memory_item_store():
    from backend.app.services.stores.postgres.memory_item_store import MemoryItemStore

    return MemoryItemStore()


def _get_memory_version_store():
    from backend.app.services.stores.postgres.memory_version_store import (
        MemoryVersionStore,
    )

    return MemoryVersionStore()


def _get_memory_evidence_link_store():
    from backend.app.services.stores.postgres.memory_evidence_link_store import (
        MemoryEvidenceLinkStore,
    )

    return MemoryEvidenceLinkStore()


def _get_memory_edge_store():
    from backend.app.services.stores.postgres.memory_edge_store import MemoryEdgeStore

    return MemoryEdgeStore()


def _get_memory_promotion_service():
    from backend.app.services.memory.promotion_service import MemoryPromotionService

    return MemoryPromotionService()


def _get_personal_knowledge_store():
    from backend.app.services.stores.postgres.personal_knowledge_store import (
        PersonalKnowledgeStore,
    )

    return PersonalKnowledgeStore()


def _get_goal_ledger_store():
    from backend.app.services.stores.postgres.goal_ledger_store import GoalLedgerStore

    return GoalLedgerStore()


def _get_meeting_session_store():
    from backend.app.services.stores.meeting_session_store import MeetingSessionStore

    return MeetingSessionStore()


def _get_memory_impact_graph_read_model():
    return MemoryImpactGraphReadModel(
        meeting_session_store=_get_meeting_session_store(),
        memory_item_store=_get_memory_item_store(),
    )


async def _load_workspace_memory_item(workspace_id: str, memory_item_id: str):
    store = _get_memory_item_store()
    item = await asyncio.to_thread(store.get, memory_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory item not found")
    if item.context_type != "workspace" or item.context_id != workspace_id:
        raise HTTPException(status_code=404, detail="Memory item not found in workspace")
    return item


def _get_store() -> GovernanceStore:
    return GovernanceStore()
