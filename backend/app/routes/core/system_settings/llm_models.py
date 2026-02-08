"""
LLM Models endpoints - Facade Module

This module has been refactored into the llm/ subpackage.
All endpoints are now defined in:
- llm/models.py: Model CRUD (get, toggle, config, test, pull)
- llm/chat_embedding.py: Chat/embedding settings and migration helpers
- llm/capability_profiles.py: Capability profile configuration
- llm/utility_configs.py: Model utility configuration

This file re-exports the combined router for backward compatibility.
"""

from .llm import router

__all__ = ["router"]
