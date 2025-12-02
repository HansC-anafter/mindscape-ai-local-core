"""
Shared 層
工具函式、LLM adapter、DB、config 等共用功能
"""

# 暫時 re-export，之後慢慢整理
from backend.app.core.security import security_monitor
from backend.app.services.backend_manager import BackendManager
from backend.app.services.unified_tool_executor import UnifiedToolExecutor

__all__ = [
    "security_monitor",
    "BackendManager",
    "UnifiedToolExecutor",
]
