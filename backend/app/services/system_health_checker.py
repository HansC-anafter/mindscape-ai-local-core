"""
System Health Checker Service

Checks system health status including:
- LLM API key configuration
- Vector DB connection
- Tool connections (WordPress, Obsidian, Notion, etc.)
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional, TypeVar

from backend.app.services.backend_manager import BackendManager
from backend.app.services.config_store import ConfigStore
from backend.app.services.system_health_llm import SystemHealthLlmMixin
from backend.app.services.system_health_models import HealthIssue, HealthIssueSeverity
from backend.app.services.system_health_resources import SystemHealthResourceMixin
from backend.app.services.system_health_tools import SystemHealthToolConnectionMixin
from backend.app.services.tool_registry import ToolRegistryService

T = TypeVar("T")


async def run_readiness_coro_in_worker(
    coro_factory: Callable[[], Awaitable[T]],
) -> T:
    """Run readiness checks away from the API event loop.

    System/workspace health intentionally performs real DB, LLM, OCR, vector, and
    tool checks. Some of those clients are synchronous, so the full readiness
    coroutine runs on a worker thread to avoid starving dependency-free
    liveness.
    """

    def _run() -> T:
        return asyncio.run(coro_factory())

    return await asyncio.to_thread(_run)


class SystemHealthChecker(
    SystemHealthLlmMixin,
    SystemHealthResourceMixin,
    SystemHealthToolConnectionMixin,
):
    """System health checker service"""

    def __init__(
        self,
        config_store: Optional[ConfigStore] = None,
        tool_registry: Optional[ToolRegistryService] = None,
        backend_manager: Optional[BackendManager] = None
    ):
        import os
        from backend.app.routes.core.tools.base import get_tool_registry
        
        self.config_store = config_store or ConfigStore()
        # Use cached global tool registry to avoid overhead on every health check
        self.tool_registry = tool_registry or get_tool_registry()
        self.backend_manager = backend_manager or BackendManager(config_store=self.config_store)

    async def check_workspace_health(
        self,
        profile_id: str,
        workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check system health for a workspace

        Args:
            profile_id: User profile ID
            workspace_id: Optional workspace ID

        Returns:
            Health status dictionary
        """
        issues: List[HealthIssue] = []
        tools_status: Dict[str, Dict[str, Any]] = {}

        # Check backend service
        backend_status = await self._check_backend_service(issues)

        # Check OCR service
        ocr_status = await self._check_ocr_service(issues)

        # Check LLM configuration
        llm_status = await self._check_llm_configuration(profile_id, issues)

        # Check Vector DB connection
        vector_db_status = await self._check_vector_db(issues)

        # Check tool connections
        tools_status = await self._check_tool_connections(profile_id, issues)

        return {
            "backend": backend_status,
            "ocr_service": ocr_status,
            "llm_configured": llm_status["configured"],
            "llm_provider": llm_status.get("provider"),
            "llm_available": llm_status.get("available", False),
            "vector_db_connected": vector_db_status["connected"],
            "tools": tools_status,
            "issues": [issue.to_dict() for issue in issues],
            "overall_status": "healthy" if not any(i.severity == HealthIssueSeverity.ERROR for i in issues) else "unhealthy"
        }


__all__ = [
    "HealthIssue",
    "HealthIssueSeverity",
    "SystemHealthChecker",
    "run_readiness_coro_in_worker",
]
