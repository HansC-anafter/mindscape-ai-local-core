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
import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_WATCHDOG_STATE_DIR = Path(
    os.getenv("MULTIMODAL_WATCHDOG_STATE_DIR", "/app/logs/mlx-watchdog")
)
_WATCHDOG_STATE_FILE = _WATCHDOG_STATE_DIR / "inflight_request.json"
_WATCHDOG_HEARTBEAT_TTL_SECONDS = max(
    1,
    int(os.getenv("MLX_WATCHDOG_INFLIGHT_HEARTBEAT_TTL", "45")),
)
_WATCHDOG_HARD_TIMEOUT_SECONDS = max(
    _WATCHDOG_HEARTBEAT_TTL_SECONDS,
    int(os.getenv("MLX_WATCHDOG_INFLIGHT_HARD_TIMEOUT", "720")),
)
_WATCHDOG_PREFILL_TIMEOUT_SECONDS = max(
    _WATCHDOG_HEARTBEAT_TTL_SECONDS,
    int(os.getenv("MLX_WATCHDOG_INFLIGHT_PREFILL_TIMEOUT", "1800")),
)


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

    async def check_playbook_deps(
        self,
        playbook_code: str,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Return list of unmet dependency names for a playbook.

        Returns empty list if all deps are met or playbook has no deps.
        """
        deps = await self._resolve_playbook_dependencies(
            playbook_code,
            execution_context=execution_context,
        )
        if not deps:
            return []

        unmet = []
        for dep in deps:
            if not await self._check_dep(dep):
                unmet.append(dep)
        return unmet

    async def _resolve_playbook_dependencies(
        self,
        playbook_code: str,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        deps = list(PLAYBOOK_DEPENDENCIES.get(playbook_code, []))
        if not deps:
            return []

        if playbook_code != "ig_analyze_pinned_reference":
            return deps

        workspace_id = self._extract_workspace_id(execution_context)
        if not workspace_id:
            return deps

        resolved_scope = self._resolve_reference_runtime_scope(
            workspace_id,
            execution_context=execution_context,
        )
        if resolved_scope == "cloud":
            logger.info(
                "Skipping local MLX dependency gate for %s because workspace=%s resolves to cloud vision runtime",
                playbook_code,
                workspace_id,
            )
            return []

        return deps

    def _resolve_reference_runtime_scope(
        self,
        workspace_id: str,
        *,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        try:
            from backend.app.capabilities.ig.services.vision_runtime_policy import (
                extract_reference_execution_intent_from_inputs,
                resolve_reference_execution_intent,
            )

            inputs = (
                execution_context.get("inputs")
                if isinstance(execution_context, dict)
                and isinstance(execution_context.get("inputs"), dict)
                else None
            )
            intent = extract_reference_execution_intent_from_inputs(inputs)
            resolution = resolve_reference_execution_intent(
                intent,
                workspace_id=workspace_id,
            )
            resolved_scope = str(resolution.get("resolved_scope") or "").strip().lower()
            if resolved_scope in {"cloud", "local"}:
                return resolved_scope
        except Exception as exc:
            logger.warning(
                "Failed to resolve vision runtime policy for dependency check workspace=%s: %s",
                workspace_id,
                exc,
            )

        # Stay conservative if policy resolution breaks or returns nothing.
        return "local"

    @staticmethod
    def _extract_workspace_id(
        execution_context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if not isinstance(execution_context, dict):
            return None

        workspace_id = str(execution_context.get("workspace_id") or "").strip()
        if workspace_id:
            return workspace_id

        inputs = execution_context.get("inputs")
        if isinstance(inputs, dict):
            workspace_id = str(inputs.get("workspace_id") or "").strip()
            if workspace_id:
                return workspace_id
        return None

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
        """Check MLX liveness with a real HTTP probe plus watchdog fallback.

        `/v1/models` proves the server is answering requests. When the single
        worker is busy, that endpoint can still stall; in that case accept a
        fresh watchdog heartbeat as evidence that the in-flight request is
        making progress instead of treating MLX as dead.
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
            request = (
                f"GET /v1/models HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii")
            writer.write(request)
            await asyncio.wait_for(writer.drain(), timeout=1.0)
            status_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            if b"200" in status_line:
                return True, None
            if self._mlx_watchdog_is_fresh():
                return True, None
            if status_line:
                return False, status_line.decode("ascii", errors="replace").strip()
            return False, "empty http response"
        except TimeoutError:
            if self._mlx_watchdog_is_fresh():
                return True, None
            return False, "mlx http timeout"
        except (ConnectionRefusedError, socket.gaierror, OSError) as e:
            if self._mlx_watchdog_is_fresh():
                return True, None
            return False, str(e)
        except Exception as e:
            if self._mlx_watchdog_is_fresh():
                return True, None
            return False, str(e)

    def _mlx_watchdog_is_fresh(self) -> bool:
        try:
            if not _WATCHDOG_STATE_FILE.exists():
                return False
            payload = json.loads(_WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False
            if str(payload.get("status") or "").strip().lower() != "active":
                return False

            now = time.time()
            heartbeat_at = self._safe_float(payload.get("heartbeat_at_epoch"))
            progress_at = self._safe_float(payload.get("progress_at_epoch"))
            phase_entered_at = self._safe_float(payload.get("phase_entered_at_epoch"))
            started_at = self._safe_float(payload.get("started_at_epoch"))
            phase = str(payload.get("progress_phase") or "").strip().lower()

            request_age = max(0.0, now - started_at) if started_at else 0.0
            heartbeat_age = max(0.0, now - heartbeat_at) if heartbeat_at else float("inf")
            progress_age = max(0.0, now - progress_at) if progress_at else float("inf")
            phase_age = max(
                0.0,
                now - (phase_entered_at or started_at),
            ) if (phase_entered_at or started_at) else request_age

            prefill_phases = {"accepted", "embedding", "prefill", "model_loading"}
            active_inference_phases = {"model_ready", "decode_ready", "generating"}

            if progress_age <= _WATCHDOG_HEARTBEAT_TTL_SECONDS:
                return True
            if phase in prefill_phases and phase_age <= _WATCHDOG_PREFILL_TIMEOUT_SECONDS:
                return True
            if phase in active_inference_phases and request_age < _WATCHDOG_HARD_TIMEOUT_SECONDS:
                return True
            if heartbeat_age <= _WATCHDOG_HEARTBEAT_TTL_SECONDS:
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def _safe_float(value: object) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
