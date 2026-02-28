"""
Compatibility shim for legacy module path.

Playbook routes have been split into the package:
    app.routes.core.playbook

This file intentionally re-exports the package-level router/shared symbols to
avoid stale duplicated route logic.
"""

from .playbook import router, mindscape_store, playbook_service

__all__ = ["router", "mindscape_store", "playbook_service"]
