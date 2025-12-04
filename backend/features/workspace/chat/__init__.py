"""
Workspace Chat Module

Refactored modular chat implementation with separated concerns:
- handlers/: Request handlers (CTA, suggestions, messages)
- streaming/: Streaming response generation
- playbook/: Playbook trigger and execution
- utils/: Utility functions (LLM provider, token management)
"""

from .routes import router

__all__ = ['router']

