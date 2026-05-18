"""Intent route compatibility facade."""

from .intents_core.detail_routes import (
    create_intent,
    delete_intent,
    get_intent,
    update_intent,
)
from .intents_core.list_routes import list_intents
from .intents_core.router import router
from .intents_core.schemas import (
    CreateIntentRequest,
    IntentResponse,
    IntentTreeNode,
    ListIntentsResponse,
    ListIntentsTreeResponse,
    UpdateIntentRequest,
)
from .intents_core.serializers import build_intent_tree, intent_card_to_response
from .intents_core.state import _utc_now, logger, store

__all__ = [
    "CreateIntentRequest",
    "IntentResponse",
    "IntentTreeNode",
    "ListIntentsResponse",
    "ListIntentsTreeResponse",
    "UpdateIntentRequest",
    "_utc_now",
    "build_intent_tree",
    "create_intent",
    "delete_intent",
    "get_intent",
    "intent_card_to_response",
    "list_intents",
    "logger",
    "router",
    "store",
    "update_intent",
]
