"""Compatibility facade for chat and embedding model routes."""

from .chat_embedding_core.router import router
from .chat_embedding_core.state import _utc_now
from .chat_embedding_core.settings_routes import (
    get_llm_model_settings,
    update_chat_model,
    update_embedding_model,
)
from .chat_embedding_core.chat_test_routes import test_chat_model_connection
from .chat_embedding_core.embedding_test_routes import test_embedding_model_connection
from .chat_embedding_core.migration_analysis import _analyze_embedding_migration_needs

__all__ = [
    "router",
    "_utc_now",
    "get_llm_model_settings",
    "update_chat_model",
    "update_embedding_model",
    "test_chat_model_connection",
    "test_embedding_model_connection",
    "_analyze_embedding_migration_needs",
]
