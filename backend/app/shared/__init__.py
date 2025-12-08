"""
Shared layer

Common utilities including tool functions, LLM adapters, database, and configuration.
"""

# Temporary re-export, will be refactored later
from backend.app.core.security import security_monitor
from backend.app.services.backend_manager import BackendManager
from backend.app.services.unified_tool_executor import UnifiedToolExecutor

__all__ = [
    "security_monitor",
    "BackendManager",
    "UnifiedToolExecutor",
]
