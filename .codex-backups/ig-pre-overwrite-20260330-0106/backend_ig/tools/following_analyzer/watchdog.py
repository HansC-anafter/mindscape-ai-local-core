"""
Watchdog thread for Instagram following analyzer.

This module provides a background heartbeat to keep progress artifacts
updated even when the main async flow stalls.  It also monitors the DB
task status and signals the runner to abort when the task has been
cancelled or failed externally.
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .artifact_manager import ArtifactManager

logger = logging.getLogger(__name__)


class ProgressWatchdog:
    """
    Background thread that keeps progress artifacts alive with heartbeat updates.

    This prevents the UI from going stale when the main async flow is blocked
    (e.g., waiting for slow Playwright operations).

    Additionally, it checks the DB task status on each heartbeat cycle and sets
    an ``abort_requested`` event if the task has been cancelled or failed
    externally, allowing the runner to break out of its loops gracefully.
    """

    def __init__(
        self,
        artifact_manager: "ArtifactManager",
        interval_sec: Optional[float] = None,
        stale_sec: Optional[float] = None,
        task_id: Optional[str] = None,
    ):
        self.artifact_manager = artifact_manager
        self.interval_sec = interval_sec or float(
            os.environ.get("IG_PROGRESS_WATCHDOG_INTERVAL_SEC") or 15
        )
        self.stale_sec = stale_sec or float(
            os.environ.get("IG_PROGRESS_WATCHDOG_STALE_SEC") or 90
        )
        self._task_id = task_id

        self._stop_event = threading.Event()
        self._abort_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Page-index stall detection: abort if page_index unchanged for N cycles
        self._last_page_index = -1
        self._page_index_stale_count = 0
        self._max_page_index_stale = int(
            os.environ.get("IG_WATCHDOG_MAX_STALE_CYCLES") or 20
        )
        self._tasks_store = None  # lazy init

    # ── Public API ───────────────────────────────────────────────

    def start(self) -> None:
        """Start the watchdog background thread."""
        if self._thread is not None:
            return  # Already running

        self._stop_event.clear()
        self._abort_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.debug("[IGFollowingAnalyzer] Watchdog thread started")

    def stop(self) -> None:
        """Stop the watchdog background thread."""
        self._stop_event.set()
        if self._thread is not None:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
            self._thread = None
        logger.debug("[IGFollowingAnalyzer] Watchdog thread stopped")

    def is_abort_requested(self) -> bool:
        """Check whether the runner should abort (non-blocking)."""
        return self._abort_event.is_set()

    # ── Internal ─────────────────────────────────────────────────

    def _get_tasks_store(self):
        """Lazy-init a TasksStore instance."""
        if self._tasks_store is None:
            try:
                from backend.app.services.stores.tasks_store import TasksStore

                self._tasks_store = TasksStore()
            except Exception as exc:
                logger.debug("[Watchdog] Cannot create TasksStore: %s", exc)
        return self._tasks_store

    def _check_task_status(self) -> None:
        """Query the DB task status and set abort if cancelled/failed."""
        task_id = self._task_id or getattr(self.artifact_manager, "trace_id", None)
        if not task_id:
            return

        try:
            store = self._get_tasks_store()
            if not store:
                return

            should_abort = store.should_abort_task(task_id)
            if should_abort:
                logger.warning(
                    "[IGFollowingAnalyzer] Watchdog detected abort signal for task %s",
                    task_id,
                )
                self._abort_event.set()
        except Exception as exc:
            # Never let status check crash the watchdog loop
            logger.debug("[IGFollowingAnalyzer] Watchdog status check error: %s", exc)

    def _persist_abort_signal(
        self,
        reason: str,
        *,
        accounts: Optional[List[Dict[str, Any]]] = None,
        progress: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist a structured watchdog-abort signal for the parent runner."""
        task_id = self._task_id or getattr(self.artifact_manager, "trace_id", None)
        requested_at = _utc_now().isoformat()
        accounts_list = accounts if isinstance(accounts, list) else []
        progress_map = dict(progress or {})
        previous_stage = progress_map.get("stage")

        abort_progress = dict(progress_map)
        abort_progress["stage"] = "error"
        abort_progress["error_type"] = "watchdog_stall"
        abort_progress["error_message"] = reason[:800]
        abort_progress["watchdog_abort_requested"] = True
        abort_progress["watchdog_abort_requested_at"] = requested_at
        abort_progress["watchdog_abort_reason"] = reason
        if previous_stage:
            abort_progress["watchdog_abort_stage"] = previous_stage

        try:
            self.artifact_manager.update_artifact_sync(accounts_list, abort_progress)
        except Exception as exc:
            logger.debug("[Watchdog] Failed to persist abort artifact: %s", exc)

        if not task_id:
            return
        try:
            store = self._get_tasks_store()
            if not store:
                return
            task = store.get_task(task_id)
            if not task:
                return
            ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
            ctx2 = dict(ctx)
            ctx2["watchdog_abort_requested_at"] = requested_at
            ctx2["watchdog_abort_reason"] = reason
            ctx2["watchdog_abort"] = {
                "requested_at": requested_at,
                "reason": reason,
                "stage": previous_stage,
                "page_index": abort_progress.get("page_index"),
                "page_total": abort_progress.get("page_total"),
                "current_account": abort_progress.get("current_account"),
                "error_type": abort_progress.get("error_type"),
            }
            store.update_task(task_id, execution_context=ctx2)
        except Exception as exc:
            logger.debug("[Watchdog] Failed to persist abort task signal: %s", exc)

    def _loop(self) -> None:
        """
        Main watchdog loop.

        Only kicks in when progress hasn't updated for a while (avoids noisy
        writes during healthy runs).
        """
        while not self._stop_event.is_set():
            try:
                # ── Always check task status (cheap DB read) ─────
                self._check_task_status()
                if self._abort_event.is_set():
                    break  # Stop heartbeating once abort is signalled

                if not self.artifact_manager.artifacts_store:
                    self._stop_event.wait(self.interval_sec)
                    continue

                state = self.artifact_manager.get_watchdog_state()
                last_ts = float(state.get("last_upsert_ts") or 0)
                acc = state.get("accounts") or []
                prog = dict(state.get("progress") or {})
                aid = state.get("artifact_id")

                # ── Page-index stall detection ──────────────────
                page_index = prog.get("page_index", -1)
                if isinstance(page_index, int) and page_index >= 0:
                    if page_index == self._last_page_index:
                        self._page_index_stale_count += 1
                        if self._page_index_stale_count >= self._max_page_index_stale:
                            reason = (
                                "Watchdog abort: visiting_pages stalled at "
                                f"page_index={page_index} for "
                                f"{self._page_index_stale_count} cycles"
                            )
                            logger.warning(
                                "[Watchdog] page_index stalled at %d for %d cycles, aborting",
                                page_index,
                                self._page_index_stale_count,
                            )
                            self._persist_abort_signal(
                                reason,
                                accounts=acc,
                                progress=prog,
                            )
                            self._abort_event.set()
                            break
                    else:
                        self._page_index_stale_count = 0
                    self._last_page_index = page_index

                now = time.time()
                if not aid or (now - last_ts) < self.stale_sec:
                    self._stop_event.wait(self.interval_sec)
                    continue

                # Write a lightweight heartbeat update (re-using last known accounts/progress).
                prog2 = dict(prog)
                prog2["watchdog_heartbeat"] = True
                prog2["watchdog_at"] = _utc_now().isoformat()

                try:
                    self.artifact_manager.update_artifact_sync(acc, prog2)
                except Exception:
                    pass

            except Exception:
                pass

            self._stop_event.wait(self.interval_sec)


def create_and_start_watchdog(
    artifact_manager: "ArtifactManager",
    task_id: Optional[str] = None,
) -> Optional["ProgressWatchdog"]:
    """
    Create and start a watchdog if conditions are met.

    Returns the watchdog instance, or None if not started.
    """
    if not artifact_manager.artifacts_store:
        return None
    if not artifact_manager.workspace_id:
        return None
    if not artifact_manager.trace_id:
        return None

    watchdog = ProgressWatchdog(
        artifact_manager,
        task_id=task_id or artifact_manager.trace_id,
    )
    watchdog.start()
    return watchdog
