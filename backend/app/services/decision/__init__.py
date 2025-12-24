"""
Decision Coordination Services

Provides unified decision coordination integrating Intent, Playbook,
Node Governance, Cost Governance, Memory, and Policy layers.
"""

from .coordinator import (
    UnifiedDecisionCoordinator,  # Main class (kept for backward compatibility)
    IntentRoutingDecision,
    PlaybookCandidate,
    UnifiedDecisionResult
)
from .coordinator_factory import (
    create_decision_coordinator,
    create_unified_decision_coordinator  # Backward compatibility alias
)

# Type alias for cleaner usage (DecisionCoordinator is the preferred name)
DecisionCoordinator = UnifiedDecisionCoordinator

__all__ = [
    "UnifiedDecisionCoordinator",  # Primary export (backward compatible)
    "DecisionCoordinator",  # Alias for cleaner usage
    "IntentRoutingDecision",
    "PlaybookCandidate",
    "UnifiedDecisionResult",
    "create_decision_coordinator",
    "create_unified_decision_coordinator",  # Backward compatibility
]
