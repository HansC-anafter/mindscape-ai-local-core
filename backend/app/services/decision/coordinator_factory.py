"""
Decision Coordinator Factory

Factory function for creating DecisionCoordinator instances with governance stubs
"""

from typing import Optional

try:
    # Try container path first (app.*)
    from app.services.mindscape_store import MindscapeStore
    from app.services.intent_analyzer import IntentPipeline
    from app.services.decision.coordinator import UnifiedDecisionCoordinator
    from app.services.governance import (
        PlaybookPreflight,
        NodeGovernance,
        CostGovernance,
        PolicyService,
        MemoryService as MemoryServiceStub
    )
except ImportError:
    # Fallback to local path (backend.app.*)
    from backend.app.services.mindscape_store import MindscapeStore
    from backend.app.services.intent_analyzer import IntentPipeline
    from backend.app.services.decision.coordinator import UnifiedDecisionCoordinator
    from backend.app.services.governance import (
        PlaybookPreflight,
        NodeGovernance,
        CostGovernance,
        PolicyService,
        MemoryServiceStub
    )


def create_decision_coordinator(
    store: Optional[MindscapeStore] = None,
    use_stubs: bool = True
) -> UnifiedDecisionCoordinator:
    """
    Create DecisionCoordinator instance

    Args:
        store: MindscapeStore instance (if None, create new instance)
        use_stubs: Whether to use Stubs (default True, must use before implementation)

    Returns:
        DecisionCoordinator instance (UnifiedDecisionCoordinator)
    """
    if store is None:
        store = MindscapeStore()

    # IntentPipeline requires PlaybookService
    try:
        from app.services.playbook_service import PlaybookService
    except ImportError:
        from backend.app.services.playbook_service import PlaybookService

    playbook_service = PlaybookService(store=store)
    intent_pipeline = IntentPipeline(store=store, playbook_service=playbook_service)

    # Use real implementations (stubs are now replaced with real implementations)
    return UnifiedDecisionCoordinator(
        intent_pipeline=intent_pipeline,
        playbook_preflight=PlaybookPreflight(),
        node_governance=NodeGovernance(),
        cost_governance=CostGovernance(),
        memory_service=MemoryServiceStub(),  # MemoryService still uses stub
        policy_service=PolicyService()
    )


# Backward compatibility alias
create_unified_decision_coordinator = create_decision_coordinator

