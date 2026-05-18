"""Availability helpers for host bridge runtime adapter."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class AvailabilityMixin:
    async def is_available(self, workspace_id: str = None) -> bool:
        """Check if the host bridge runtime is actually connected."""
        detail = self.get_availability_detail(workspace_id=workspace_id)
        return detail["available"]

    def get_availability_detail(self, workspace_id: str = None) -> dict:
        """Return structured availability info for API responses."""
        import time

        now = time.monotonic()
        cache_key = workspace_id

        if not hasattr(self, "_ws_avail_cache"):
            self._ws_avail_cache = {}

        cached = self._ws_avail_cache.get(cache_key)
        if cached and (now - cached[1]) < 30.0:
            return cached[0]

        self._resolve_ws_manager()

        available = False
        transport = None
        reason = "unknown"

        if self.strategy == "ws":
            ws_connected = self.ws_manager is not None and (
                hasattr(self.ws_manager, "has_connections")
                and self.ws_manager.has_connections(
                    workspace_id=workspace_id,
                    surface_type=self.RUNTIME_NAME,
                )
            )
            if ws_connected:
                available = True
                transport = "ws"
                reason = "ws_connected"
            elif self._has_registered_runtime_polling_fallback(workspace_id):
                available = True
                transport = "polling"
                reason = "registered_runtime_polling_fallback"
            else:
                available = False
                transport = None
                reason = "no_ws_client"
        elif self.strategy == "polling":
            available = self._has_active_polling_runners()
            transport = "polling" if available else None
            reason = "runner_heartbeat_active" if available else "no_active_runner"
        elif self.strategy == "sampling":
            available = self.sampling_gate is not None and self.mcp_server is not None
            transport = "sampling" if available else None
            reason = "mcp_server_injected" if available else "no_mcp_server"
        else:
            logger.warning(f"Unknown strategy: {self.strategy}")
            reason = f"unknown_strategy_{self.strategy}"

        detail = {
            "available": available,
            "transport": transport,
            "reason": reason,
        }

        self._ws_avail_cache[cache_key] = (detail, now)
        self._available_cache = available
        self._available_cache_time = now
        self._available_detail_cache = detail

        if available:
            self._version_cache = "runtime-connected"
            logger.info(
                "%s adapter available via '%s' transport",
                self.RUNTIME_NAME,
                transport,
            )
        else:
            logger.debug("%s adapter not available: %s", self.RUNTIME_NAME, reason)

        return detail

    def _has_registered_runtime_polling_fallback(
        self,
        workspace_id: Optional[str] = None,
    ) -> bool:
        if self.RUNTIME_NAME != "codex_cli":
            return False
        try:
            from backend.app.services.codex_pool_runtime_router import (
                resolve_codex_pool_runtime_bundle_sync,
            )
            from backend.app.services.external_agents.bridge.codex_cli_runner import (
                resolve_codex_cli_binary,
            )

            bundle = resolve_codex_pool_runtime_bundle_sync(
                workspace_id=workspace_id or "",
                lease_owner_type=None,
                lease_owner_id=None,
            )
            if "env" not in bundle or bundle.get("error"):
                return False
            env = dict(bundle.get("env") or {})
            codex_home = str(env.get("CODEX_HOME") or "").strip()
            if not codex_home or not os.path.isdir(codex_home):
                return False
            binary = resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH"))
            if not binary or binary == "codex":
                return False
            return True
        except Exception as exc:
            logger.debug(
                "Failed to resolve registered runtime polling fallback for %s: %s",
                workspace_id,
                exc,
            )
            return False

    def _has_active_polling_runners(self) -> bool:
        """Check if the runner container is alive via its PostgreSQL heartbeat."""
        try:
            from backend.app.services.stores.tasks_store import TasksStore

            tasks_store = TasksStore()
            return tasks_store.has_active_runner(max_age_seconds=120.0)
        except Exception as e:
            logger.debug(f"Failed to check for active polling runners: {e}")
            return False
