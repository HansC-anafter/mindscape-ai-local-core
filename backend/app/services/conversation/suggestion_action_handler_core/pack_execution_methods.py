"""Execution method helpers for suggestion execute_pack."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.core.domain_context import LocalDomainContext

logger = logging.getLogger(__name__)


async def execute_pack_executor(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    pack_id: str,
    pack_id_lower: str,
    original_message_id: str,
    files,
    message: str,
    project_id: Optional[str],
    task: Optional[Any],
    action_params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Execute packs handled by coordinator-specific pack executors."""
    if pack_id_lower == "daily_planning":
        return await handler.execution_coordinator._execute_daily_planning(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            message_id=original_message_id,
            files=files,
            message=message,
            task_event_callback=None,
        )
    if pack_id_lower == "semantic_seeds" or "intent" in pack_id_lower:
        return await handler.execution_coordinator._execute_semantic_seeds(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            message_id=original_message_id,
            files=files,
            message=message,
            task_event_callback=None,
        )
    if pack_id_lower == "content_drafting":
        output_type = action_params.get("output_type", "summary")
        return await handler.execution_coordinator._execute_content_drafting(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            message_id=original_message_id,
            files=files,
            message=message,
            output_type=output_type,
            task_event_callback=None,
        )

    logger.warning(
        "Pack %s has pack_executor but no specific handler, using ExecutionPlan",
        pack_id,
    )
    return await handler._execute_via_plan(
        pack_id,
        ctx,
        original_message_id,
        files,
        message,
        project_id,
        task,
        action_params,
    )


async def execute_playbook_method(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    pack_id: str,
    playbook_found: Optional[str],
    registry: Any,
    files,
    message: str,
    task: Optional[Any],
    action_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a pack through a resolved playbook."""
    if playbook_found:
        logger.info(
            "Executing pack %s via playbook %s (found by PlaybookService)",
            pack_id,
            playbook_found,
        )
        execution_result = await handler.playbook_runner.start_playbook_execution(
            playbook_code=playbook_found,
            profile_id=ctx.actor_id,
            inputs={
                **(task.params if task and task.params else {}),
                **(action_params if action_params else {}),
                "files": files,
                "message": message,
            },
            workspace_id=ctx.workspace_id,
        )
        return {
            "pack_id": pack_id,
            "playbook_code": playbook_found,
            "execution_id": execution_result.get("execution_id"),
        }

    playbooks = registry.get_capability_playbooks(pack_id)
    if not playbooks:
        raise ValueError(
            f"Pack {pack_id} marked as playbook but no playbooks found in PlaybookService or CapabilityRegistry"
        )

    playbook_found = await find_playbook_for_pack(
        handler=handler,
        ctx=ctx,
        pack_id=pack_id,
        playbooks=playbooks,
    )
    if not playbook_found:
        from backend.app.services.i18n_service import get_i18n_service

        i18n = get_i18n_service(default_locale=handler.default_locale)
        playbook_codes_to_try = build_playbook_codes_to_try(pack_id, playbooks)
        logger.error(
            "Could not find playbook for pack %s. Tried codes: %s.",
            pack_id,
            playbook_codes_to_try,
        )
        error_msg = i18n.t(
            "conversation_orchestrator",
            "error.could_not_find_playbook",
            pack_id=pack_id,
            tried=str(playbook_codes_to_try),
        )
        raise ValueError(error_msg)

    logger.info("Executing pack %s via playbook %s", pack_id, playbook_found)
    execution_result = await handler.playbook_runner.start_playbook_execution(
        playbook_code=playbook_found,
        profile_id=ctx.actor_id,
        inputs={
            **(task.params if task and task.params else {}),
            **(action_params if action_params else {}),
            "files": files,
            "message": message,
        },
        workspace_id=ctx.workspace_id,
    )
    return {
        "pack_id": pack_id,
        "playbook_code": playbook_found,
        "execution_id": execution_result.get("execution_id"),
    }


async def execute_unknown_method(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    pack_id: str,
    pack_id_lower: str,
    registry: Any,
    original_message_id: str,
    files,
    message: str,
    project_id: Optional[str],
    task: Optional[Any],
    action_params: Dict[str, Any],
    prior_result: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Execute the legacy non-playbook branch."""
    del prior_result

    execution_method = registry.get_execution_method(pack_id)
    if execution_method == "unknown":
        error_msg = (
            f"Pack {pack_id} has unknown execution method and cannot be executed. "
            "This pack is not a playbook, does not have a pack_executor, and cannot be executed."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    if pack_id_lower == "intent_extraction":
        error_msg = (
            "SuggestionActionHandler: intent_extraction reached fallback logic. "
            "This should have been handled by IntentInfraService priority logic above. "
            "Check that priority handling is working correctly."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(
        "Pack %s has unknown execution method, trying to find playbook directly",
        pack_id,
    )
    playbook_found = None
    try:
        playbook = await handler.playbook_service.get_playbook(
            playbook_code=pack_id,
            locale=handler.default_locale,
            workspace_id=ctx.workspace_id,
        )
        if playbook:
            playbook_found = playbook.metadata.playbook_code
            logger.info(
                "Found playbook %s for pack %s (direct lookup)",
                playbook_found,
                pack_id,
            )
    except Exception as exc:
        logger.debug("Playbook %s not found via direct lookup: %s", pack_id, exc)

    if playbook_found:
        logger.info("Executing pack %s via playbook %s", pack_id, playbook_found)
        execution_result = await handler.playbook_runner.start_playbook_execution(
            playbook_code=playbook_found,
            profile_id=ctx.actor_id,
            inputs={
                **(task.params if task and task.params else {}),
                **(action_params if action_params else {}),
                "files": files,
                "message": message,
            },
            workspace_id=ctx.workspace_id,
        )
        return {
            "pack_id": pack_id,
            "playbook_code": playbook_found,
            "execution_id": execution_result.get("execution_id"),
        }

    logger.warning(
        "Pack %s has unknown execution method and no playbook found, trying ExecutionPlan as fallback",
        pack_id,
    )
    result = await handler._execute_via_plan(
        pack_id,
        ctx,
        original_message_id,
        files,
        message,
        project_id,
        task,
        action_params,
    )
    if result and result.get("suggestion_cards"):
        logger.error(
            "Pack %s execution failed - created suggestion cards, preventing infinite loop by raising error",
            pack_id,
        )
        raise ValueError(
            f"Pack {pack_id} cannot be executed: no playbook found and execution failed"
        )
    return result


def build_playbook_codes_to_try(pack_id: str, playbooks) -> list[str]:
    """Build the legacy candidate list for playbook lookup."""
    playbook_codes_to_try = [pack_id]
    for playbook_filename in playbooks:
        base_name = playbook_filename.replace(".yaml", "").replace(".yml", "")
        playbook_codes_to_try.append(base_name)
    return playbook_codes_to_try


async def find_playbook_for_pack(
    *,
    handler: Any,
    ctx: LocalDomainContext,
    pack_id: str,
    playbooks,
) -> Optional[str]:
    """Find the playbook code matching a pack."""
    playbook_codes_to_try = build_playbook_codes_to_try(pack_id, playbooks)
    logger.info(
        "Looking for playbook for pack %s, trying codes: %s",
        pack_id,
        playbook_codes_to_try,
    )
    for playbook_code in playbook_codes_to_try:
        try:
            playbook = await handler.playbook_service.get_playbook(
                playbook_code=playbook_code,
                locale=handler.default_locale,
                workspace_id=ctx.workspace_id,
            )
            if playbook:
                playbook_found = playbook.metadata.playbook_code
                logger.info(
                    "Found playbook %s for pack %s (searched with: %s)",
                    playbook_found,
                    pack_id,
                    playbook_code,
                )
                return playbook_found
        except Exception as exc:
            logger.debug("Playbook %s not found: %s", playbook_code, exc)

    logger.info("Trying to load all playbooks to find match for pack %s", pack_id)
    try:
        all_playbooks_metadata = await handler.playbook_service.list_playbooks(
            workspace_id=ctx.workspace_id,
            locale=handler.default_locale,
        )
        logger.info(
            "Loaded %s total playbooks, searching for pack %s",
            len(all_playbooks_metadata),
            pack_id,
        )
        for playbook_meta in all_playbooks_metadata:
            playbook_code = playbook_meta.playbook_code
            if playbook_code in playbook_codes_to_try:
                logger.info(
                    "Found playbook %s for pack %s via full search (exact match)",
                    playbook_code,
                    pack_id,
                )
                return playbook_code
            if pack_id.lower() in playbook_code.lower():
                logger.info(
                    "Found playbook %s for pack %s via full search (partial match)",
                    playbook_code,
                    pack_id,
                )
                return playbook_code
        logger.warning(
            "Available playbook codes: %s",
            [playbook.playbook_code for playbook in all_playbooks_metadata[:10]],
        )
    except Exception as exc:
        logger.error("Failed to load all playbooks: %s", exc, exc_info=True)
    return None


def is_valid_result(result: Optional[Dict[str, Any]], pack_id_lower: str) -> bool:
    """Return whether the legacy execute-pack result counts as successful."""
    return bool(
        result
        and (
            result.get("execution_id")
            or (result.get("executed_tasks") and not result.get("suggestion_cards"))
            or (
                pack_id_lower == "intent_extraction"
                and result.get("intents_added") is not None
            )
        )
    )
