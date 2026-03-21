"""Runner dependency health checks.

Provides per-playbook dependency checking so that tasks requiring
unavailable services (e.g. MLX vision server) remain pending instead
of being claimed and failing.

Usage from worker.py:
    checker = DependencyChecker()
    unmet = await checker.check_playbook_deps("ig_analyze_pinned_reference")
    if unmet:
        # hold task, don't claim
"""

import asyncio
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Playbook → dependency mapping ──
# Unknown playbooks default to no dependency checks (always claimable).
PLAYBOOK_DEPENDENCIES: Dict[str, List[str]] = {
    "ig_analyze_pinned_reference": ["mlx"],
    # Add more as needed:
    # "some_vision_playbook": ["mlx"],
}


@dataclass
class _DepCheckResult:
    """Single dependency check result with caching."""
    available: bool = False
    checked_at: float = 0.0  # time.monotonic()
    error: Optional[str] = None


class DependencyChecker:
    """Cached, async dependency health checker.

    Each dependency is checked at most once per `cache_ttl` seconds.
    """

    def __init__(self, cache_ttl: float = 5.0):
        self._cache: Dict[str, _DepCheckResult] = {}
        self._cache_ttl = cache_ttl

    async def check_playbook_deps(self, playbook_code: str) -> List[str]:
        """Return list of unmet dependency names for a playbook.

        Returns empty list if all deps are met or playbook has no deps.
        """
        deps = PLAYBOOK_DEPENDENCIES.get(playbook_code, [])
        if not deps:
            return []

        unmet = []
        for dep in deps:
            if not await self._check_dep(dep):
                unmet.append(dep)
        return unmet

    async def _check_dep(self, dep: str) -> bool:
        """Check a single dependency, using cache if fresh."""
        cached = self._cache.get(dep)
        now = time.monotonic()
        if cached and (now - cached.checked_at) < self._cache_ttl:
            return cached.available

        result = _DepCheckResult(checked_at=now)

        if dep == "mlx":
            result.available, result.error = await self._check_mlx()
        else:
            # Unknown dep → assume available
            result.available = True

        self._cache[dep] = result

        if not result.available:
            logger.debug(
                f"Dependency '{dep}' unavailable: {result.error}"
            )

        return result.available

    async def _check_mlx(self) -> tuple[bool, Optional[str]]:
        """Check MLX liveness with a cheap TCP connect.

        `/v1/models` can stall while the single-worker MLX server is busy with
        inference, which would incorrectly hold queued tasks in dependency
        backoff. For runner scheduling we only need to know whether the service
        is reachable at all; actual per-task serialization is handled by the
        playbook concurrency lock.
        """
        port = os.getenv("MLX_PORT", "8210")
        # Inside Docker → host.docker.internal; on host → localhost
        host = os.getenv(
            "MLX_HOST_FROM_RUNNER",
            "host.docker.internal"
        )

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, int(port)),
                timeout=1.0,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True, None
        except TimeoutError:
            return False, "tcp timeout"
        except (ConnectionRefusedError, socket.gaierror, OSError) as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
