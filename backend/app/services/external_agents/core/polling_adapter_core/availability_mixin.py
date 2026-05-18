from .base import *
from .payload import build_dispatch_payload


class PollingAvailabilityMixin:

    async def is_available(self, **kwargs) -> bool:
        """
        Check if this runtime's CLI is actually installed on the host.

        Uses shutil.which() to detect CLI binaries. Results are cached
        for 30 seconds to avoid repeated subprocess lookups.
        """
        import shutil
        import time

        now = time.monotonic()
        if (
            self._available_cache is not None
            and hasattr(self, "_available_cache_time")
            and (now - self._available_cache_time) < 30.0
        ):
            return self._available_cache

        try:
            from backend.app.routes.core.system_settings.governance_tools import (
                AGENT_CLI_MAP,
            )

            agent_info = AGENT_CLI_MAP.get(self.RUNTIME_NAME)
            if not agent_info:
                # Agent not in CLI map — cannot verify installation
                self._available_cache = False
                self._available_cache_time = now
                self._version_cache = "not-in-cli-map"
                return False

            command = agent_info["command"]
            cli_path = shutil.which(command)

            if cli_path:
                self._available_cache = True
                self._available_cache_time = now
                self._version_cache = f"cli-detected:{cli_path}"
                logger.info(f"{self.RUNTIME_NAME} CLI available at {cli_path}")
                return True

            self._available_cache = False
            self._available_cache_time = now
            self._version_cache = "cli-not-found"
            logger.debug(f"{self.RUNTIME_NAME} CLI not found (tried: {command})")
            return False

        except Exception as e:
            logger.warning(f"CLI detection failed for {self.RUNTIME_NAME}: {e}")
            self._available_cache = False
            self._available_cache_time = now
            return False
