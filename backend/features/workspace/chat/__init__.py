"""
Workspace Chat Module

Refactored modular chat implementation with separated concerns:
- handlers/: Request handlers (CTA, suggestions, messages)
- streaming/: Streaming response generation
- playbook/: Playbook trigger and execution
- utils/: Utility functions (LLM provider, token management)
"""

def __getattr__(name):
    if name == "router":
        from .routes import router

        return router
    raise AttributeError(name)


__all__ = ["router"]
