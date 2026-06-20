"""Playbook webhook helper for ``GovernanceEngine``."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def process_playbook_webhook(
    engine: Any,
    *,
    execution_id: str,
    playbook_code: str,
    user_id: str,
    output_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Handle playbook completion webhooks through the governance facade."""
    logger.info(
        "GovernanceEngine.process_playbook_webhook: ingress=%s exec=%s pb=%s",
        "playbook_webhook",
        execution_id,
        playbook_code,
    )
    onboarding_codes = {
        "project_breakdown_onboarding",
        "weekly_review_onboarding",
    }
    if playbook_code in onboarding_codes:
        logger.info(
            "GovernanceEngine: delegating onboarding playbook=%s to legacy handler",
            playbook_code,
        )
        try:
            return await engine._invoke_legacy_webhook_handler(
                execution_id=execution_id,
                playbook_code=playbook_code,
                user_id=user_id,
                output_data=output_data,
                hook="handle_playbook_completion",
            )
        except Exception as exc:
            logger.error("GovernanceEngine: onboarding delegation failed: %s", exc)
            return {"success": False, "error": str(exc)}

    workspace_id = engine._resolve_workspace_id(
        execution_id=execution_id,
        output_data=output_data,
    )
    completion_result = engine.process_completion(
        workspace_id=workspace_id,
        execution_id=execution_id,
        result_data=output_data,
        playbook_code=playbook_code,
    ) or {"success": False}

    response: Dict[str, Any] = {
        **completion_result,
        "playbook_code": playbook_code,
        "created_resources": {},
    }

    if completion_result.get("success"):
        try:
            post_landing = await engine._invoke_legacy_webhook_handler(
                execution_id=execution_id,
                playbook_code=playbook_code,
                user_id=user_id,
                output_data=output_data,
                hook="handle_post_landing_completion",
            )
            if isinstance(post_landing, dict):
                response["created_resources"] = post_landing.get(
                    "created_resources", {}
                )
                if post_landing.get("message"):
                    response["message"] = post_landing["message"]
                response["post_landing_hook"] = post_landing
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: regular post-landing hook failed (non-fatal): %s",
                exc,
            )

    return response


async def invoke_legacy_webhook_handler(
    *,
    execution_id: str,
    playbook_code: str,
    user_id: str,
    output_data: Dict[str, Any],
    hook: str,
) -> Dict[str, Any]:
    """Invoke legacy webhook hooks behind a single adapter boundary."""
    from backend.app.services.mindscape_store import MindscapeStore
    from backend.app.services.playbook_webhook import PlaybookWebhookHandler

    handler = PlaybookWebhookHandler(MindscapeStore())
    method = getattr(handler, hook)
    return await method(
        execution_id=execution_id,
        playbook_code=playbook_code,
        user_id=user_id,
        output_data=output_data,
    )
