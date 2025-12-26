"""
Migration script: Migrate from chat_model to capability profile system

This script derives initial capability profile configuration from existing chat_model setting.
"""

import sys
import logging
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


def migrate_chat_model_to_capability_profile():
    """
    Migrate from chat_model to capability profile configuration

    Migration logic:
    1. Read existing chat_model
    2. Derive default capability profile mapping based on model name
    3. Set capability_profile_mapping and profile_model_mapping
    """
    settings_store = SystemSettingsStore()
    chat_setting = settings_store.get_setting("chat_model")

    if not chat_setting:
        logger.info("No chat_model setting found, skipping migration")
        return

    model_name = str(chat_setting.value)
    logger.info(f"Migrating from chat_model: {model_name}")

    # Derive default profile based on model name
    model_lower = model_name.lower()
    if "gpt-4" in model_lower or "claude-3-opus" in model_lower or "gemini-2.0-pro" in model_lower:
        # Strong model -> default to "precise" profile
        default_profile = "precise"
    elif "gpt-3.5" in model_lower or "claude-3-haiku" in model_lower or "gemini-1.5-flash" in model_lower:
        # Fast model -> default to "fast" profile
        default_profile = "fast"
    else:
        # Other -> default to "standard" profile
        default_profile = "standard"

    logger.info(f"Derived default profile: {default_profile}")

    # Set default stage to profile mapping
    default_mapping = {
        "intent_analysis": "fast",
        "plan_generation": default_profile,
        "tool_call_generation": "tool_strict",
        "response_formatting": "standard",
    }

    settings_store.set_capability_profile_mapping(default_mapping)
    logger.info(f"Set capability_profile_mapping: {default_mapping}")

    # Set profile to model mapping (from chat_model)
    profile_model_mapping = {
        "fast": [model_name, "gpt-3.5-turbo", "claude-3-haiku", "gemini-1.5-flash"],
        "standard": [model_name, "gpt-4o", "claude-3-sonnet", "gemini-1.5-pro"],
        "precise": [model_name, "gpt-4", "claude-3-opus", "gemini-2.0-pro"],
        "tool_strict": [model_name, "gpt-4", "claude-3-opus"],
        "safe_write": [model_name, "gpt-4", "claude-3-opus"],
    }

    settings_store.set_profile_model_mapping(profile_model_mapping)
    logger.info(f"Set profile_model_mapping for {len(profile_model_mapping)} profiles")

    logger.info("Migration completed successfully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_chat_model_to_capability_profile()









