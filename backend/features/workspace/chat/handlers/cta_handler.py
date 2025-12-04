"""
CTA (Call-to-Action) handler for workspace chat
"""

import logging
from typing import Dict, Any

from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)


async def handle_cta_action(
    orchestrator: ConversationOrchestrator,
    workspace_id: str,
    profile_id: str,
    timeline_item_id: str,
    action: str,
    confirm: bool,
    project_id: str
) -> Dict[str, Any]:
    """
    Handle CTA action request

    Args:
        orchestrator: Conversation orchestrator
        workspace_id: Workspace ID
        profile_id: Profile ID
        timeline_item_id: Timeline item ID
        action: Action type
        confirm: Confirmation flag
        project_id: Project ID

    Returns:
        Response dict
    """
    result = await orchestrator.handle_cta(
        workspace_id=workspace_id,
        profile_id=profile_id,
        timeline_item_id=timeline_item_id,
        action=action,
        confirm=confirm,
        project_id=project_id
    )
    return result

