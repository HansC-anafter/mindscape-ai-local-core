"""
Backward-compatibility facade for agent_websocket.

All code has been refactored into the agent_dispatch/ package.
This module re-exports the public API so existing imports continue to work:

    from backend.app.routes.agent_websocket import router
    from backend.app.routes.agent_websocket import get_agent_dispatch_manager
    from backend.app.routes.agent_websocket import PendingTask, InflightTask
"""

from .agent_dispatch import *  # noqa: F401,F403
from .agent_dispatch import router  # noqa: F401
