"""
Playbook trigger detection and execution
"""

import logging
import re
from typing import Dict, Any, Optional

from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# Playbook trigger pattern: [EXECUTE_PLAYBOOK: playbook_code]
PLAYBOOK_TRIGGER_PATTERN = re.compile(r'\[EXECUTE_PLAYBOOK:\s*([a-zA-Z0-9_-]+)\]')


async def check_and_trigger_playbook(
    full_text: str,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    execution_mode: str
) -> Optional[Dict[str, Any]]:
    """
    Check if LLM response contains playbook trigger marker and execute if found

    Args:
        full_text: Full LLM response text
        workspace: Workspace object
        workspace_id: Workspace ID
        profile_id: User profile ID
        execution_mode: Current execution mode

    Returns:
        Dict with execution info if triggered, None otherwise
    """
    logger.info(f"[PlaybookTrigger] Checking for playbook trigger. execution_mode={execution_mode}, text_length={len(full_text)}")

    # Only process triggers in execution mode (as fallback)
    # Hybrid mode uses IntentPipeline instead of LLM-generated markers
    if execution_mode != "execution":
        logger.info(f"[PlaybookTrigger] Skipping trigger check: execution_mode='{execution_mode}' is not 'execution' (hybrid mode uses IntentPipeline)")
        return None

    # Find playbook trigger marker
    match = PLAYBOOK_TRIGGER_PATTERN.search(full_text)
    if not match:
        logger.info(f"[PlaybookTrigger] No playbook trigger marker found in response text")
        # Log a sample of the text for debugging
        sample_text = full_text[:200] + "..." if len(full_text) > 200 else full_text
        logger.debug(f"[PlaybookTrigger] Response text sample: {sample_text}")
        return None

    playbook_code = match.group(1)
    logger.info(f"[PlaybookTrigger] Found trigger for playbook: {playbook_code}")

    try:
        from backend.app.services.playbook_service import PlaybookService, ExecutionMode as PlaybookExecutionMode
        from backend.app.services.mindscape_store import MindscapeStore

        # Use PlaybookService instead of legacy APIs
        store = MindscapeStore()
        playbook_service = PlaybookService(store=store)

        # Verify playbook exists
        playbook = await playbook_service.get_playbook(
            playbook_code=playbook_code,
            locale=workspace.default_locale,
            workspace_id=workspace_id
        )
        if not playbook:
            error_msg = f"Playbook '{playbook_code}' not found"
            logger.error(f"[PlaybookTrigger] {error_msg}")
            return {
                "status": "error",
                "playbook_code": playbook_code,
                "message": f"Playbook '{playbook_code}' not found"
            }

        # Execute playbook
        execution_result = await playbook_service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            profile_id=profile_id,
            inputs=None,
            execution_mode=PlaybookExecutionMode.ASYNC,
            locale=workspace.default_locale
        )

        # Convert ExecutionResult to dict format for backward compatibility
        result = {
            "execution_id": execution_result.execution_id,
            "execution_mode": "workflow" if execution_result.status == "running" else "conversation",
            "result": execution_result.result or {},
        }

        logger.info(f"[PlaybookTrigger] Playbook {playbook_code} executed successfully")
        return {
            "status": "triggered",
            "playbook_code": playbook_code,
            "playbook_name": playbook.metadata.name if playbook else playbook_code,
            "execution_mode": result.get("execution_mode", "workflow"),
            "execution_id": result.get("execution_id") or result.get("result", {}).get("execution_id")
        }

    except Exception as e:
        logger.error(f"[PlaybookTrigger] Failed to execute playbook {playbook_code}: {e}", exc_info=True)
        from backend.app.shared.error_handler import format_playbook_error
        return format_playbook_error(playbook_code, e)

