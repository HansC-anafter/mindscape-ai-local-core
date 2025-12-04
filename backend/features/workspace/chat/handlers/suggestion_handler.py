"""
Suggestion action handler for workspace chat
"""

import logging
import uuid
from typing import Dict, Any, Optional

from backend.app.services.conversation_orchestrator import ConversationOrchestrator

logger = logging.getLogger(__name__)


async def handle_suggestion_action(
    orchestrator: ConversationOrchestrator,
    workspace_id: str,
    profile_id: str,
    action: str,
    action_params: Dict[str, Any],
    project_id: str,
    message_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Handle suggestion action request

    Args:
        orchestrator: Conversation orchestrator
        workspace_id: Workspace ID
        profile_id: Profile ID
        action: Action type
        action_params: Action parameters
        project_id: Project ID
        message_id: Optional message ID

    Returns:
        Response dict
    """
    # Generate message_id if not provided
    if not message_id:
        message_id = str(uuid.uuid4())

    result = await orchestrator.handle_suggestion_action(
        workspace_id=workspace_id,
        profile_id=profile_id,
        action=action,
        action_params=action_params or {},
        project_id=project_id,
        message_id=message_id
    )
    return result

