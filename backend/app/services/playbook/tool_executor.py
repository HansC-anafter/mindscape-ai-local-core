"""
Playbook Tool Executor (Deprecated Monolith)
This file is now a facade import for backward compatibility. 
The actual implementation has been decomposed into `backend/app/services/playbook/tool_execution/`.
"""

import logging

logger = logging.getLogger(__name__)

# Ensure filesystem tools are registered (cross-process via Redis)
def _init_filesystem_tools():
    """
    Register filesystem tools with cross-process coordination via Redis.
    Called at module import and before tool execution.
    """
    try:
        from backend.app.services.tools.registry import (
            register_filesystem_tools,
            _mindscape_tools,
        )
        from backend.app.services.cache.redis_cache import get_cache_service

        required = [
            "filesystem_list_files",
            "filesystem_read_file",
            "filesystem_write_file",
            "filesystem_search",
        ]
        missing = [t for t in required if t not in _mindscape_tools]

        if not missing:
            return  # All tools already registered

        logger.info(
            f"PlaybookToolExecutor: Registering filesystem tools (missing: {missing})"
        )
        register_filesystem_tools()

        # Verify and set Redis marker
        still_missing = [t for t in required if t not in _mindscape_tools]
        if still_missing:
            logger.error(f"PlaybookToolExecutor: Failed to register: {still_missing}")
        else:
            logger.info(
                f"PlaybookToolExecutor: Successfully registered filesystem tools"
            )
            try:
                cache = get_cache_service()
                cache.set("builtin_tools:filesystem:registered", "true", ttl=3600)
            except Exception:
                pass  # Non-critical

    except Exception as e:
        logger.error(
            f"PlaybookToolExecutor: Failed to init filesystem tools: {e}", exc_info=True
        )

_init_filesystem_tools()

# Expose internal helpers if needed by other legacy code
from backend.app.services.playbook.tool_execution.events import _utc_now

# Forward PlaybookToolExecutor
from backend.app.services.playbook.tool_execution.executor import PlaybookToolExecutor

__all__ = ["PlaybookToolExecutor", "_utc_now", "_init_filesystem_tools"]
