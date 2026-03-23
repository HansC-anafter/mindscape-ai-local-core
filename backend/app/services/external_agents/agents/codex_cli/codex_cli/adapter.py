"""
Codex CLI Agent Adapter

Dispatches coding tasks to OpenAI Codex CLI via the shared
REST Polling + DB-primary pipeline.

All dispatch lifecycle logic is inherited from PollingAgentAdapter.
"""

import logging

from backend.app.services.external_agents.core.polling_adapter import (
    PollingAgentAdapter,
)

logger = logging.getLogger(__name__)


class CodexCLIAdapter(PollingAgentAdapter):
    """
    Codex CLI Agent Adapter.

    Dispatches coding tasks to OpenAI Codex CLI via the shared
    polling-based dispatch pipeline. All lifecycle logic (DB persistence,
    Future notification, timeout recovery) is inherited.
    """

    RUNTIME_NAME = "codex_cli"
    RUNTIME_VERSION = "1.0.0"
    AGENT_NAME = RUNTIME_NAME
    AGENT_VERSION = RUNTIME_VERSION

    # Codex may need longer execution time
    RESULT_TIMEOUT: float = 900.0

    async def is_available(self, workspace_id: str = None, **kwargs) -> bool:
        detail = self.get_availability_detail(workspace_id=workspace_id)
        return detail["available"]

    def get_availability_detail(self, workspace_id: str = None) -> dict:
        try:
            from backend.app.routes.agent_dispatch import get_agent_dispatch_manager

            manager = get_agent_dispatch_manager()
            if manager.has_connections(
                workspace_id=workspace_id,
                surface_type=self.RUNTIME_NAME,
            ):
                self._available_cache = True
                self._version_cache = "runtime-connected"
                return {
                    "available": True,
                    "transport": "ws",
                    "reason": "ws_connected",
                }
        except Exception as exc:
            logger.debug("Codex CLI availability probe failed: %s", exc)

        reason = "no_surface_bridge"
        try:
            from backend.app.services.stores.tasks_store import TasksStore

            if not TasksStore().has_active_runner(max_age_seconds=120.0):
                reason = "no_active_runner"
        except Exception:
            reason = "availability_probe_failed"

        self._available_cache = False
        self._version_cache = reason
        return {
            "available": False,
            "transport": None,
            "reason": reason,
        }
