"""
Background dispatcher for accepted compile jobs.

Compile requests persist an accepted job first. This manager polls persisted
jobs, claims them atomically, and schedules the actual compile work out of band
from the request lifecycle.
"""

import asyncio
import logging
from typing import Optional

from backend.app.services.compile_job_reconciler import CompileJobReconciler

logger = logging.getLogger(__name__)


class CompileJobDispatchManager:
    """Runtime background consumer for accepted compile jobs."""

    def __init__(
        self,
        *,
        reconciler: Optional[CompileJobReconciler] = None,
        poll_interval_seconds: float = 1.0,
        batch_limit: int = 10,
    ) -> None:
        self._reconciler = reconciler
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_limit = batch_limit
        self._consumer_task: Optional[asyncio.Task] = None
        self._wake_event: Optional[asyncio.Event] = None

    def start_background_services(self) -> None:
        """Start the compile job dispatch consumer if not already running."""
        if self._consumer_task and not self._consumer_task.done():
            return
        if self._wake_event is None:
            self._wake_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        self._consumer_task = loop.create_task(self.consume_pending_compile_jobs())
        logger.info("Compile job dispatch consumer started")

    def stop_background_services(self) -> None:
        """Stop the compile job dispatch consumer."""
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            logger.info("Compile job dispatch consumer stopped")
        self._consumer_task = None
        if self._wake_event is not None:
            self._wake_event.set()

    def notify_pending_job(self) -> None:
        """Wake the consumer early when a new accepted job is inserted."""
        if self._wake_event is not None:
            self._wake_event.set()

    async def consume_pending_compile_jobs(self) -> None:
        """Continuously poll and claim accepted compile jobs."""
        logger.info("Starting compile job dispatch consumer loop")
        while True:
            try:
                summary = await self._reconciler_instance.dispatch_pending_accepted_jobs(
                    limit=self._batch_limit,
                )
                if self._should_continue_draining(summary):
                    await asyncio.sleep(0)
                    continue
                await self._wait_for_work()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Compile job dispatch consumer iteration failed")
                await asyncio.sleep(self._poll_interval_seconds)

    @property
    def _reconciler_instance(self) -> CompileJobReconciler:
        if self._reconciler is None:
            from backend.app.services.stores.compile_job_store import CompileJobStore
            from backend.app.services.stores.meeting_session_store import (
                MeetingSessionStore,
            )

            self._reconciler = CompileJobReconciler(
                compile_job_store=CompileJobStore(),
                meeting_session_store=MeetingSessionStore(),
            )
        return self._reconciler

    def _should_continue_draining(self, summary: dict[str, int]) -> bool:
        if summary["inspected"] >= self._batch_limit:
            return True
        return any(
            summary[key] > 0
            for key in (
                "resumed",
                "succeeded",
                "failed",
                "session_failed",
            )
        )

    async def _wait_for_work(self) -> None:
        if self._wake_event is None:
            self._wake_event = asyncio.Event()
        try:
            await asyncio.wait_for(
                self._wake_event.wait(),
                timeout=self._poll_interval_seconds,
            )
        except asyncio.TimeoutError:
            return
        finally:
            self._wake_event.clear()


compile_job_dispatch_manager = CompileJobDispatchManager()


def get_compile_job_dispatch_manager() -> CompileJobDispatchManager:
    """Return the process-local compile job dispatch manager singleton."""
    return compile_job_dispatch_manager
