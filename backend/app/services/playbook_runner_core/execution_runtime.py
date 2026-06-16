"""Shared runtime helpers for playbook runner execution turns."""

import logging
from typing import Any, Optional

from backend.app.services.executor_route_context import load_executor_route_context
from backend.app.services.llm.workspace_routed_chat import (
    chat_completion_with_workspace_route,
)

logger = logging.getLogger(__name__)


async def load_and_apply_executor_route_context(
    runner: Any,
    conv_manager: Any,
    workspace_id: Optional[str],
    *,
    reuse_existing: bool = False,
) -> Any:
    """Load executor route context and mirror it into the tool executor."""
    route_context = (
        getattr(conv_manager, "executor_route_context", None) if reuse_existing else None
    )
    if route_context is None and workspace_id:
        route_context = await load_executor_route_context(workspace_id)

    setattr(conv_manager, "executor_route_context", route_context)
    if route_context:
        runner.tool_executor.execution_context["executor_route_context"] = route_context
    else:
        runner.tool_executor.execution_context.pop("executor_route_context", None)
    return route_context


def get_llm_provider(runner: Any, profile_id: str) -> Any:
    """Resolve the configured LLM provider for a profile."""
    llm_manager = runner.llm_provider_manager.get_llm_manager(profile_id)
    return runner.llm_provider_manager.get_llm_provider(llm_manager)


async def run_playbook_chat_completion(
    *,
    runner: Any,
    conv_manager: Any,
    profile_id: str,
    provider: Any,
    route_context: Any,
    purpose: str,
    workspace_id: Optional[str],
    log_playbook_code: Optional[str] = None,
) -> str:
    """Run one LLM response and append it to the conversation."""
    messages = await conv_manager.get_messages_for_llm()
    if log_playbook_code:
        logger.info(
            f"PlaybookRunner: Calling LLM for playbook {log_playbook_code}, messages_count={len(messages)}"
        )

    assistant_response = await chat_completion_with_workspace_route(
        messages=messages,
        workspace_id=workspace_id,
        profile_id=profile_id,
        max_tokens=8192,
        provider=provider,
        llm_provider_manager=runner.llm_provider_manager,
        route_context=route_context,
        purpose=purpose,
    )

    if log_playbook_code:
        logger.info(
            f"PlaybookRunner: LLM response received for playbook {log_playbook_code}, response_length={len(assistant_response) if assistant_response else 0}"
        )

    conv_manager.add_assistant_message(assistant_response)
    return assistant_response


async def run_playbook_tool_loop(
    *,
    runner: Any,
    conv_manager: Any,
    assistant_response: str,
    execution_id: str,
    profile_id: str,
    provider: Any,
    workspace_id: Optional[str],
    sandbox_id: Optional[str],
    max_iterations: int,
    log_tool_loop: bool = False,
    swallow_tool_loop_errors: bool = False,
) -> tuple[str, list[Any]]:
    """Run the tool loop for an assistant response."""
    if log_tool_loop:
        logger.info(f"PlaybookRunner: Starting tool execution loop for {execution_id}")

    try:
        assistant_response, used_tools = await runner.tool_executor.execute_tool_loop(
            conv_manager=conv_manager,
            assistant_response=assistant_response,
            execution_id=execution_id,
            profile_id=profile_id,
            provider=provider,
            model_name=None,
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
            max_iterations=max_iterations,
        )
    except Exception as exc:
        if not swallow_tool_loop_errors:
            raise
        logger.error(
            f"PlaybookRunner: Tool execution loop failed for {execution_id}: {exc}",
            exc_info=True,
        )
        used_tools = []
    else:
        if log_tool_loop:
            logger.info(
                f"PlaybookRunner: Tool execution loop completed for {execution_id}, used_tools={len(used_tools) if used_tools else 0}"
            )

    return assistant_response, used_tools


async def run_playbook_assistant_turn(
    *,
    runner: Any,
    conv_manager: Any,
    execution_id: str,
    profile_id: str,
    provider: Any,
    route_context: Any,
    purpose: str,
    workspace_id: Optional[str],
    sandbox_id: Optional[str],
    max_iterations: int,
    log_playbook_code: Optional[str] = None,
    log_tool_loop: bool = False,
    swallow_tool_loop_errors: bool = False,
) -> tuple[str, list[Any]]:
    """Run one LLM response and its follow-up tool loop."""
    assistant_response = await run_playbook_chat_completion(
        runner=runner,
        conv_manager=conv_manager,
        profile_id=profile_id,
        provider=provider,
        route_context=route_context,
        purpose=purpose,
        workspace_id=workspace_id,
        log_playbook_code=log_playbook_code,
    )
    return await run_playbook_tool_loop(
        runner=runner,
        conv_manager=conv_manager,
        assistant_response=assistant_response,
        execution_id=execution_id,
        profile_id=profile_id,
        provider=provider,
        workspace_id=workspace_id,
        sandbox_id=sandbox_id,
        max_iterations=max_iterations,
        log_tool_loop=log_tool_loop,
        swallow_tool_loop_errors=swallow_tool_loop_errors,
    )
