"""Decision cards route compatibility facade."""

from .decision_cards_core.break_glass_routes import (
    approve_break_glass,
    list_break_glass_permissions,
    request_break_glass,
    revoke_break_glass,
)
from .decision_cards_core.card_routes import (
    assign_decision_card,
    confirm_decision,
    list_decision_cards,
)
from .decision_cards_core.router import router
from .decision_cards_core.schemas import (
    BreakGlassApprovalModel,
    BreakGlassRequestModel,
    ConfirmDecisionRequest,
)
from .decision_cards_core.state import _utc_now, logger

__all__ = [
    "BreakGlassApprovalModel",
    "BreakGlassRequestModel",
    "ConfirmDecisionRequest",
    "_utc_now",
    "approve_break_glass",
    "assign_decision_card",
    "confirm_decision",
    "list_break_glass_permissions",
    "list_decision_cards",
    "logger",
    "request_break_glass",
    "revoke_break_glass",
    "router",
]
