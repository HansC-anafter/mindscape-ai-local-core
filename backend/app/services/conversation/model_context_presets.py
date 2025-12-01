"""
Model Context Presets

Defines context window limits for different LLM models based on their context size.
Used by ContextBuilder to optimize history length and message limits.
"""

from typing import Optional

# Model context presets based on context window size
MODEL_CONTEXT_PRESETS = {
    # Large context models (128k+ tokens)
    "gpt-5.1": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
        "MAX_CONTEXT_TOKENS": 16385,  # Actual model limit (gpt-3.5-turbo based on errors)
    },
    "gpt-5.1-thinking": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
    },
    "gpt-4.1": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
    },
    "gpt-4.1-mini": {
        "MAX_EVENTS_FOR_QUERY": 40,
        "MAX_HISTORY_MESSAGES": 16,
        "MAX_MESSAGE_CHARS": 1000,
        "HISTORY_TOKEN_BUDGET": 8000,
    },
    "gpt-4-turbo": {
        "MAX_EVENTS_FOR_QUERY": 64,
        "MAX_HISTORY_MESSAGES": 24,
        "MAX_MESSAGE_CHARS": 1500,
        "HISTORY_TOKEN_BUDGET": 16000,
    },
    "gpt-4o": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
    },
    "claude-3-5-sonnet": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
    },
    "claude-3-opus": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
    },

    # Medium context models (32k-64k tokens)
    "gpt-4": {
        "MAX_EVENTS_FOR_QUERY": 40,
        "MAX_HISTORY_MESSAGES": 16,
        "MAX_MESSAGE_CHARS": 1000,
        "HISTORY_TOKEN_BUDGET": 8000,
    },
    "gpt-3.5-turbo": {
        "MAX_EVENTS_FOR_QUERY": 40,
        "MAX_HISTORY_MESSAGES": 16,
        "MAX_MESSAGE_CHARS": 1000,
        "HISTORY_TOKEN_BUDGET": 8000,
    },
    "claude-3-sonnet": {
        "MAX_EVENTS_FOR_QUERY": 40,
        "MAX_HISTORY_MESSAGES": 16,
        "MAX_MESSAGE_CHARS": 1000,
        "HISTORY_TOKEN_BUDGET": 8000,
    },
    "claude-3-haiku": {
        "MAX_EVENTS_FOR_QUERY": 40,
        "MAX_HISTORY_MESSAGES": 16,
        "MAX_MESSAGE_CHARS": 1000,
        "HISTORY_TOKEN_BUDGET": 8000,
    },

    # Small context models (8k-16k tokens)
    "gpt-3.5": {
        "MAX_EVENTS_FOR_QUERY": 20,
        "MAX_HISTORY_MESSAGES": 10,
        "MAX_MESSAGE_CHARS": 800,
        "HISTORY_TOKEN_BUDGET": 4000,
    },

    # Default fallback
    "default": {
        "MAX_EVENTS_FOR_QUERY": 200,
        "MAX_HISTORY_MESSAGES": 100,
        "MAX_MESSAGE_CHARS": 10000,
        "HISTORY_TOKEN_BUDGET": 50000,
    },
}


def get_context_preset(model_name: Optional[str] = None) -> dict:
    """
    Get context preset for a model

    Args:
        model_name: Model name (e.g., 'gpt-4.1', 'claude-3-5-sonnet')
                   If None or not found, returns default preset

    Returns:
        Dictionary with context limits:
        - MAX_EVENTS_FOR_QUERY: Max events to fetch
        - MAX_HISTORY_MESSAGES: Max conversation messages
        - MAX_MESSAGE_CHARS: Max characters per message
        - HISTORY_TOKEN_BUDGET: Token budget for history (optional)
    """
    if not model_name:
        return MODEL_CONTEXT_PRESETS["default"]

    if model_name in MODEL_CONTEXT_PRESETS:
        return MODEL_CONTEXT_PRESETS[model_name]

    for preset_name, preset in MODEL_CONTEXT_PRESETS.items():
        if preset_name != "default" and model_name.startswith(preset_name):
            return preset

    for preset_name, preset in MODEL_CONTEXT_PRESETS.items():
        if preset_name != "default" and preset_name in model_name:
            return preset

    return MODEL_CONTEXT_PRESETS["default"]


def get_model_name_from_env() -> Optional[str]:
    """
    Get model name from environment variables

    Checks:
    - OPENAI_MODEL
    - ANTHROPIC_MODEL
    - LLM_MODEL

    Returns:
        Model name or None
    """
    import os

    model_name = (
        os.getenv("OPENAI_MODEL") or
        os.getenv("ANTHROPIC_MODEL") or
        os.getenv("LLM_MODEL") or
        os.getenv("MODEL_NAME")
    )

    return model_name
