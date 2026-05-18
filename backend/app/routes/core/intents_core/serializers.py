from typing import List, Dict

from backend.app.models.mindscape import IntentCard, IntentStatus

from .schemas import IntentResponse, IntentTreeNode
from .state import _utc_now

def intent_card_to_response(
    intent_card: IntentCard, workspace_id: str
) -> IntentResponse:
    """Convert IntentCard to API response format"""

    # Map IntentStatus to API status
    status_map = {
        IntentStatus.ACTIVE: "CONFIRMED",
        IntentStatus.COMPLETED: "CONFIRMED",
        IntentStatus.ARCHIVED: "REJECTED",
        IntentStatus.PAUSED: "CANDIDATE",
    }
    api_status = status_map.get(intent_card.status, "CANDIDATE")

    return IntentResponse(
        id=intent_card.id,
        workspace_id=workspace_id,
        title=intent_card.title,
        description=intent_card.description,
        status=api_status,
        parent_id=intent_card.parent_intent_id,
        metadata=intent_card.metadata or {},
        created_at=(
            intent_card.created_at.isoformat()
            if intent_card.created_at
            else _utc_now().isoformat()
        ),
        updated_at=(
            intent_card.updated_at.isoformat()
            if intent_card.updated_at
            else _utc_now().isoformat()
        ),
    )


def build_intent_tree(
    intents: List[IntentCard], workspace_id: str
) -> List[IntentTreeNode]:
    """Build tree structure from flat intent list"""

    # Convert to response format
    intent_responses = {
        intent.id: intent_card_to_response(intent, workspace_id) for intent in intents
    }

    # Create tree nodes
    tree_nodes: Dict[str, IntentTreeNode] = {}
    root_nodes: List[IntentTreeNode] = []

    # First pass: create all nodes
    for intent in intents:
        node = IntentTreeNode(**intent_responses[intent.id].model_dump(), children=[])
        tree_nodes[intent.id] = node

    # Second pass: build tree structure
    for intent in intents:
        node = tree_nodes[intent.id]
        if intent.parent_intent_id and intent.parent_intent_id in tree_nodes:
            # Add as child
            parent_node = tree_nodes[intent.parent_intent_id]
            if parent_node.children is None:
                parent_node.children = []
            parent_node.children.append(node)
        else:
            # Root node
            root_nodes.append(node)

    return root_nodes


# ============================================================================
# API Endpoints
