"""
Token counting and context truncation utilities
"""

import logging
from typing import Tuple

from backend.app.services.conversation.context_builder import ContextBuilder

logger = logging.getLogger(__name__)

# Model context limits (input tokens)
MODEL_CONTEXT_LIMITS = {
    "gpt-3.5-turbo": 12000,
    "gpt-4": 12000,
    "gpt-4-turbo": 12000,
    "gpt-4o": 120000,
    "gpt-4o-mini": 120000,
    "gpt-5.1": 120000,
    "gpt-4.1": 120000,
}


def get_model_context_limit(model_name: str) -> int:
    """
    Get context limit for a model

    Args:
        model_name: Model name

    Returns:
        Context limit in tokens (default: 12000)
    """
    return MODEL_CONTEXT_LIMITS.get(model_name, 12000)


def estimate_token_count(text: str, model_name: str) -> int:
    """
    Estimate token count for text

    Args:
        text: Text to estimate
        model_name: Model name for tokenizer

    Returns:
        Estimated token count
    """
    context_builder = ContextBuilder(model_name=model_name)
    return context_builder.estimate_token_count(text, model_name) or 0


def truncate_context_if_needed(
    system_part: str,
    user_part: str,
    model_name: str
) -> Tuple[str, int, int]:
    """
    Truncate system context if it exceeds model's token limit

    Priority order for truncation:
    1. Keep workspace context, intents, tasks first
    2. Then timeline
    3. Then conversation history

    Args:
        system_part: System prompt part
        user_part: User message part
        model_name: Model name for token limit

    Returns:
        Tuple of (truncated_system_part, system_tokens, total_tokens)
    """
    max_input_tokens = get_model_context_limit(model_name)
    context_builder = ContextBuilder(model_name=model_name)

    # Estimate initial token counts
    system_tokens = context_builder.estimate_token_count(system_part, model_name) or 0
    user_tokens = context_builder.estimate_token_count(user_part, model_name) or 0
    total_tokens = system_tokens + user_tokens

    logger.info(f"Token count check - System: {system_tokens}, User: {user_tokens}, Total: {total_tokens}, Limit: {max_input_tokens}")

    # If within limit, return as-is
    if total_tokens <= max_input_tokens:
        return system_part, system_tokens, total_tokens

    # Truncate conversation history first
    excess_tokens = total_tokens - max_input_tokens
    logger.warning(f"Context exceeds token limit by {excess_tokens} tokens, truncating system prompt...")

    if "## Recent Conversation:" in system_part:
        conv_start = system_part.find("## Recent Conversation:")
        system_part = system_part[:conv_start] + "\n## Recent Conversation:\n[Conversation history truncated due to token limit]"
        logger.info("Truncated conversation history section")

        # Re-estimate
        system_tokens = context_builder.estimate_token_count(system_part, model_name) or 0
        total_tokens = system_tokens + user_tokens

    # If still too long, truncate timeline
    if total_tokens > max_input_tokens and "## Recent Timeline Activity:" in system_part:
        timeline_start = system_part.find("## Recent Timeline Activity:")
        conv_section = "\n## Recent Conversation:\n[Conversation history truncated due to token limit]"
        system_part = system_part[:timeline_start] + "\n## Recent Timeline Activity:\n[Timeline truncated due to token limit]" + conv_section
        logger.info("Truncated timeline section")

        # Re-estimate
        system_tokens = context_builder.estimate_token_count(system_part, model_name) or 0
        total_tokens = system_tokens + user_tokens

    # Final check - if still too long, keep only essential parts
    if total_tokens > max_input_tokens:
        essential_parts = []

        # Extract essential sections
        if "## Workspace Context:" in system_part:
            ws_start = system_part.find("## Workspace Context:")
            ws_end = system_part.find("\n##", ws_start + 1)
            if ws_end == -1:
                ws_end = len(system_part)
            essential_parts.append(system_part[ws_start:ws_end])

        if "## Active Intents" in system_part:
            intents_start = system_part.find("## Active Intents")
            intents_end = system_part.find("\n##", intents_start + 1)
            if intents_end == -1:
                intents_end = len(system_part)
            essential_parts.append(system_part[intents_start:intents_end])

        if "## Current Tasks:" in system_part:
            tasks_start = system_part.find("## Current Tasks:")
            tasks_end = system_part.find("\n##", tasks_start + 1)
            if tasks_end == -1:
                tasks_end = len(system_part)
            essential_parts.append(system_part[tasks_start:tasks_end])

        # Rebuild with only essential parts
        system_instructions_start = system_part.find("You are an intelligent workspace assistant")
        if system_instructions_start != -1:
            instructions_end = system_part.find("\n## Workspace Context:")
            if instructions_end == -1:
                instructions_end = system_part.find("\n## Active Intents")
            if instructions_end != -1:
                system_instructions = system_part[system_instructions_start:instructions_end]
                system_part = system_instructions + "\n\n" + "\n\n".join(essential_parts)
                logger.warning("Truncated to essential context only (workspace, intents, tasks)")

    # Final token count
    system_tokens = context_builder.estimate_token_count(system_part, model_name) or 0
    total_tokens = system_tokens + user_tokens
    logger.info(f"After truncation - System: {system_tokens}, User: {user_tokens}, Total: {total_tokens}, Limit: {max_input_tokens}")

    return system_part, system_tokens, total_tokens

