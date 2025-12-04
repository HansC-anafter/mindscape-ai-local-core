"""
Prompt building for streaming responses
"""

import logging
from typing import List, Dict, Any, Optional

from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.shared.prompt_templates import (
    build_workspace_context_prompt,
    build_execution_mode_prompt,
    build_agent_mode_prompt
)

logger = logging.getLogger(__name__)


def build_enhanced_prompt(
    message: str,
    context: str,
    context_builder: ContextBuilder
) -> str:
    """
    Build enhanced prompt with context

    Args:
        message: User message
        context: Context string
        context_builder: ContextBuilder instance

    Returns:
        Enhanced prompt string
    """
    enhanced_prompt = context_builder.build_enhanced_prompt(
        message=message,
        context=context or ""
    )

    if enhanced_prompt is not None:
        logger.info(f"Enhanced prompt length: {len(enhanced_prompt)} chars")
        # Log enhanced_prompt to see actual content
        if "Context from this workspace:" in enhanced_prompt:
            ctx_start = enhanced_prompt.find("Context from this workspace:")
            logger.info(f"Enhanced prompt contains context at position {ctx_start}")
            logger.info(
                f"Context section preview (first 1000 chars after 'Context from this workspace:'): "
                f"{enhanced_prompt[ctx_start:ctx_start+1000]}..."
            )
        else:
            logger.warning("Enhanced prompt does NOT contain 'Context from this workspace:' marker!")
    else:
        logger.warning("Enhanced prompt is None, using empty string")
        enhanced_prompt = ""

    return enhanced_prompt


def inject_execution_mode_prompt(
    enhanced_prompt: str,
    execution_mode: str,
    locale: str,
    workspace_id: str,
    available_playbooks: List[Dict[str, Any]],
    expected_artifacts: Optional[List[str]] = None,
    execution_priority: str = "medium"
) -> str:
    """
    Inject execution mode-specific prompt into enhanced prompt

    Args:
        enhanced_prompt: Base enhanced prompt
        execution_mode: Execution mode ("execution", "hybrid", "qa")
        locale: Locale for prompt
        workspace_id: Workspace ID
        available_playbooks: List of available playbooks
        expected_artifacts: Optional list of expected artifacts
        execution_priority: Execution priority ("low", "medium", "high")

    Returns:
        Prompt with execution mode instructions injected
    """
    try:
        # Build execution mode-specific system prompt
        if execution_mode == "execution":
            workspace_system_prompt = build_execution_mode_prompt(
                preferred_language=locale,
                include_language_policy=True,
                workspace_id=workspace_id,
                available_playbooks=available_playbooks,
                expected_artifacts=expected_artifacts,
                execution_priority=execution_priority
            )
            logger.info(f"Using EXECUTION mode prompt (priority={execution_priority})")
        elif execution_mode == "hybrid":
            workspace_system_prompt = build_agent_mode_prompt(
                preferred_language=locale,
                include_language_policy=True,
                workspace_id=workspace_id,
                available_playbooks=available_playbooks,
                expected_artifacts=expected_artifacts,
                execution_priority=execution_priority
            )
            logger.info(f"Using AGENT mode prompt (priority={execution_priority})")
        else:
            workspace_system_prompt = build_workspace_context_prompt(
                preferred_language=locale,
                include_language_policy=True,
                workspace_id=workspace_id,
                available_playbooks=available_playbooks
            )
            logger.info("Using QA mode prompt")

        # Replace the base system instructions in enhanced_prompt
        if "You are an intelligent workspace assistant" in enhanced_prompt or "You are an **Execution Agent**" in enhanced_prompt:
            ctx_marker = "Context from this workspace:"
            if ctx_marker in enhanced_prompt:
                ctx_start = enhanced_prompt.find(ctx_marker)
                context_part = enhanced_prompt[ctx_start:]
                enhanced_prompt = workspace_system_prompt + "\n\n" + context_part
                logger.info(f"Injected {execution_mode} mode prompt into system prompt")
            else:
                enhanced_prompt = workspace_system_prompt + "\n\n" + enhanced_prompt
                logger.info(f"Prepended {execution_mode} mode prompt to system prompt")
        else:
            enhanced_prompt = workspace_system_prompt + "\n\n" + enhanced_prompt
            logger.info(f"Prepended {execution_mode} mode prompt to system prompt")

    except Exception as e:
        logger.warning(f"Failed to inject execution mode prompt: {e}", exc_info=True)

    return enhanced_prompt


def parse_prompt_parts(enhanced_prompt: str, user_message: str) -> tuple[str, str]:
    """
    Parse enhanced prompt into system and user parts

    Args:
        enhanced_prompt: Enhanced prompt string
        user_message: Original user message

    Returns:
        Tuple of (system_part, user_part)
    """
    if "User question:" in enhanced_prompt:
        parts = enhanced_prompt.split("User question:", 1)
        system_part = parts[0].strip()
        user_part = user_message
    else:
        # Use enhanced_prompt as system, message as user
        system_part = enhanced_prompt
        user_part = user_message

    return system_part, user_part

