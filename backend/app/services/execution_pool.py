"""
Execution Pool Dispatcher

Provides pool-aware execution routing for the distributed
architecture. Selects the best execution backend (local runner
or remote cloud) based on availability, quota, and concurrency
constraints.

This is the local-core side of the Bridge dispatch mechanism.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Quota gate defaults (overridable via environment)
DEFAULT_MAX_CONCURRENT_LOCAL = 5
DEFAULT_MAX_CONCURRENT_REMOTE = 10


class ExecutionPoolDispatcher:
    """Route execution requests to the optimal backend.

    Implements a minimal quota gate and backend selection policy.
    Local-core has no knowledge of cloud tenant details --
    the CloudConnector handles cloud-side concerns.
    """

    def __init__(self):
        self._max_local = int(
            os.getenv(
                "POOL_MAX_CONCURRENT_LOCAL",
                str(DEFAULT_MAX_CONCURRENT_LOCAL),
            )
        )
        self._max_remote = int(
            os.getenv(
                "POOL_MAX_CONCURRENT_REMOTE",
                str(DEFAULT_MAX_CONCURRENT_REMOTE),
            )
        )
        self._active_local: int = 0
        self._active_remote: int = 0

    @property
    def local_available(self) -> bool:
        """Check if local runner has capacity."""
        return self._active_local < self._max_local

    @property
    def remote_available(self) -> bool:
        """Check if remote cloud backend has capacity."""
        cloud_enabled = os.getenv("CLOUD_CONNECTOR_ENABLED", "false").lower() == "true"
        return cloud_enabled and self._active_remote < self._max_remote

    def select_backend(
        self,
        hint: Optional[str] = None,
    ) -> str:
        """Select the best execution backend.

        Selection policy (v0):
        1. If hint is explicit (runner/in_process/remote), honor it
           if the backend has capacity
        2. If hint is 'auto' or None:
           a. Prefer local runner if available
           b. Fallback to remote if local is full
           c. Fallback to in_process as last resort

        Args:
            hint: Caller-provided backend preference

        Returns:
            Selected backend: 'runner', 'in_process', or 'remote'
        """
        hint = (hint or "auto").strip().lower()

        # Explicit hints honored when capacity available
        if hint == "remote":
            if self.remote_available:
                return "remote"
            logger.warning(
                "Remote backend requested but unavailable, " "falling back to local"
            )
            hint = "auto"

        if hint == "runner":
            if self.local_available:
                return "runner"
            logger.warning(
                "Runner backend requested but at capacity (%d/%d), " "falling back",
                self._active_local,
                self._max_local,
            )
            hint = "auto"

        if hint == "in_process":
            return "in_process"

        # Auto selection: local first, then remote, then in_process
        if self.local_available:
            return "runner"
        if self.remote_available:
            return "remote"

        logger.info(
            "All backends at capacity (local=%d/%d, remote=%d/%d), " "using in_process",
            self._active_local,
            self._max_local,
            self._active_remote,
            self._max_remote,
        )
        return "in_process"

    def acquire(self, backend: str) -> bool:
        """Reserve a slot for an execution.

        Args:
            backend: Backend type to reserve

        Returns:
            True if slot acquired, False if at capacity
        """
        if backend == "runner":
            if self._active_local >= self._max_local:
                return False
            self._active_local += 1
            return True
        elif backend == "remote":
            if self._active_remote >= self._max_remote:
                return False
            self._active_remote += 1
            return True
        # in_process has no quota limit
        return True

    def release(self, backend: str) -> None:
        """Release a slot after execution completes.

        Args:
            backend: Backend type to release
        """
        if backend == "runner":
            self._active_local = max(0, self._active_local - 1)
        elif backend == "remote":
            self._active_remote = max(0, self._active_remote - 1)

    def get_stats(self) -> Dict[str, Any]:
        """Get current pool statistics for dashboard display."""
        return {
            "local": {
                "active": self._active_local,
                "max": self._max_local,
                "available": self.local_available,
            },
            "remote": {
                "active": self._active_remote,
                "max": self._max_remote,
                "available": self.remote_available,
            },
        }
