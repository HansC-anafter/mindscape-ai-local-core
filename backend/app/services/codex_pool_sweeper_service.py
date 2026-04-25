"""
Background sweeper for Codex pool requalification.

Moves due-runtime recovery out of request-time admission so degraded runtimes
can be promoted or flagged by a scheduled control-plane loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.services.codex_pool_requalification_service import (
    CodexPoolRequalificationService,
    CodexPoolRequalificationSummary,
)

logger = logging.getLogger(__name__)

_DEFAULT_SWEEP_INTERVAL_SECONDS = 300.0
_DEFAULT_SWEEP_LIMIT = 200


def _normalize_float(value: Any, *, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_int(value: Any, *, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CodexPoolSweeperService:
    """Periodic control-plane loop for Codex pool requalification."""

    def __init__(
        self,
        *,
        interval_seconds: Optional[float] = None,
        sweep_limit: Optional[int] = None,
        service_factory: Optional[Callable[[], CodexPoolRequalificationService]] = None,
    ) -> None:
        resolved_interval = interval_seconds
        if resolved_interval is None:
            resolved_interval = _normalize_float(
                os.getenv("CODEX_POOL_REQUALIFICATION_SWEEP_INTERVAL_SECONDS"),
                fallback=_DEFAULT_SWEEP_INTERVAL_SECONDS,
            )
        resolved_limit = sweep_limit
        if resolved_limit is None:
            resolved_limit = _normalize_int(
                os.getenv("CODEX_POOL_REQUALIFICATION_SWEEP_LIMIT"),
                fallback=_DEFAULT_SWEEP_LIMIT,
            )

        self._interval_seconds = max(float(resolved_interval), 0.0)
        self._sweep_limit = max(int(resolved_limit), 0)
        self._service_factory = service_factory or CodexPoolRequalificationService
        self._task: Optional[asyncio.Task[Any]] = None
        self._last_started_at: Optional[str] = None
        self._last_finished_at: Optional[str] = None
        self._last_summary: Optional[dict[str, Any]] = None
        self._last_error: Optional[str] = None
        self._status = "idle"

    @property
    def interval_seconds(self) -> float:
        return self._interval_seconds

    @property
    def enabled(self) -> bool:
        return self._interval_seconds > 0

    def snapshot_status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._task is not None and not self._task.done(),
            "interval_seconds": self._interval_seconds,
            "sweep_limit": self._sweep_limit,
            "status": self._status,
            "last_started_at": self._last_started_at,
            "last_finished_at": self._last_finished_at,
            "last_summary": dict(self._last_summary or {}),
            "last_error": self._last_error,
        }

    def start_background_services(self) -> bool:
        if not self.enabled:
            self._status = "disabled"
            logger.info(
                "Codex pool sweeper disabled "
                "(interval_seconds=%s)",
                self._interval_seconds,
            )
            return False
        if self._task is not None and not self._task.done():
            return False

        loop = asyncio.get_running_loop()
        self._task = loop.create_task(
            self._run_loop(),
            name="codex-pool-requalification-sweeper",
        )
        self._status = "scheduled"
        logger.info(
            "Codex pool sweeper scheduled "
            "(interval_seconds=%s sweep_limit=%s)",
            self._interval_seconds,
            self._sweep_limit,
        )
        return True

    def stop_background_services(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def wait_closed(self) -> None:
        if self._task is None:
            return
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run_loop(self) -> None:
        self._status = "running"
        try:
            while True:
                self._last_started_at = _utc_now().isoformat()
                summary = await asyncio.to_thread(self._run_single_sweep)
                self._last_finished_at = _utc_now().isoformat()
                self._last_summary = summary.to_payload()
                self._last_error = None
                self._status = "running"
                self._log_summary(summary)
                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            self._status = "cancelled"
            logger.info("Codex pool sweeper cancelled")
            raise
        except Exception as exc:
            self._last_finished_at = _utc_now().isoformat()
            self._last_error = str(exc)
            self._status = "failed"
            logger.warning("Codex pool sweeper failed: %s", exc, exc_info=True)
            raise

    def _run_single_sweep(self) -> CodexPoolRequalificationSummary:
        service = self._service_factory()
        return service.sweep_due_runtimes(limit=self._sweep_limit)

    def _log_summary(self, summary: CodexPoolRequalificationSummary) -> None:
        if (
            summary.requalified_runtime_count
            or summary.cooldown_cleared_count
            or summary.manual_repair_required_count
        ):
            logger.info(
                "Codex pool sweeper cycle updated pool "
                "(scanned=%s requalified=%s cooldown_cleared=%s manual_repair=%s updated=%s manual=%s)",
                summary.scanned_runtime_count,
                summary.requalified_runtime_count,
                summary.cooldown_cleared_count,
                summary.manual_repair_required_count,
                list(summary.updated_runtime_ids),
                list(summary.manual_repair_runtime_ids),
            )
        else:
            logger.debug(
                "Codex pool sweeper cycle completed "
                "(scanned=%s no_updates=true)",
                summary.scanned_runtime_count,
            )


_codex_pool_sweeper_service = CodexPoolSweeperService()


def get_codex_pool_sweeper_service() -> CodexPoolSweeperService:
    return _codex_pool_sweeper_service
