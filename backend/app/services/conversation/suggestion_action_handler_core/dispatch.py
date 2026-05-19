"""Suggestion action dispatch helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext

logger = logging.getLogger(__name__)


async def handle_action(
    handler: Any,
    *,
    workspace_id: str,
    profile_id: str,
    action: str,
    action_params: Dict[str, Any],
    project_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle action from dynamic suggestion."""
    if not action_params:
        logger.error(
            "handle_action called with None action_params for action: %s",
            action,
        )
        action_params = {}

    suggestion_id = action_params.get("suggestion_id") or action_params.get("task_id")
    ctx = LocalDomainContext(
        actor_id=profile_id,
        workspace_id=workspace_id,
        tags={"mode": "local"},
    )
    return await handler.handle_suggestion_action_with_ctx(
        ctx=ctx,
        suggestion_id=suggestion_id,
        action=action,
        action_params=action_params,
        project_id=project_id,
        message_id=message_id,
    )


async def handle_suggestion_action_with_ctx(
    handler: Any,
    *,
    ctx: LocalDomainContext,
    suggestion_id: Optional[str],
    action: str,
    action_params: Dict[str, Any],
    project_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch a suggestion action using an execution context."""
    del suggestion_id

    try:
        if action == "execute_playbook":
            return await handler._handle_execute_playbook(
                ctx,
                action_params,
                project_id,
                message_id,
            )
        if action == "use_tool":
            return await handler._handle_use_tool(
                ctx,
                action_params,
                project_id,
                message_id,
            )
        if action == "create_intent":
            return await handler._handle_create_intent(
                ctx,
                action_params,
                project_id,
                message_id,
            )
        if action == "add_to_mindscape" or action == "add_to_intents":
            return await handler._handle_add_to_mindscape(
                ctx=ctx,
                action_params=action_params,
                project_id=project_id,
                message_id=message_id,
            )
        if action == "start_chat":
            return handler._handle_start_chat(ctx.workspace_id)
        if action == "upload_file":
            return handler._handle_upload_file(ctx.workspace_id)
        if action == "execute_pack":
            return await handler._handle_execute_pack(
                ctx=ctx,
                action_params=action_params,
                project_id=project_id,
                message_id=message_id,
            )

        from backend.app.services.i18n_service import get_i18n_service

        i18n = get_i18n_service(default_locale=handler.default_locale)
        error_msg = i18n.t(
            "conversation_orchestrator",
            "error.unknown_action",
            action=action,
        )
        raise ValueError(error_msg)
    except Exception as exc:
        logger.error("Failed to handle suggestion action: %s", exc, exc_info=True)
        return handler._handle_error(
            ctx.workspace_id,
            ctx.actor_id,
            project_id,
            str(exc),
        )
