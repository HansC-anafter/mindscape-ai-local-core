from __future__ import annotations

import argparse
import queue as queue_module
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import requests

from .analysis_metrics import AnalysisStageMetrics
from .append_recovery import schedule_append_confirmation
from .api_client import append_motion_window
from .events import emit
from .guidance_delivery import GuidanceDeliveryWorker
from .guidance_socket import GuidanceSocket
from .reference_alignment import LiveReferenceAlignmentMatcher
from .windows import PendingMotionWindow


APPEND_SENDER_CLOSE_GRACE_SEC = 15.0
APPEND_ACK_CONFIRMATION_MAX_ROUNDS = 4
APPEND_RATE_LIMIT_RETRY_PADDING_SEC = 0.025


class BackgroundMotionWindowSender:
    def __init__(
        self,
        *,
        args: argparse.Namespace,
        live_session_id: str,
        practice_session_id: str,
        guidance: GuidanceSocket | None,
        reference_matcher: LiveReferenceAlignmentMatcher | None = None,
        reference_alignment_observer: Callable[[dict[str, Any]], None] | None = None,
        analysis_metrics: AnalysisStageMetrics | None = None,
    ) -> None:
        self.args = args
        self.live_session_id = live_session_id
        self.practice_session_id = practice_session_id
        self.guidance_enabled = not args.disable_guidance_ws
        self.reference_matcher = reference_matcher
        self.reference_alignment_observer = reference_alignment_observer
        self.analysis_metrics = analysis_metrics
        self.queue: queue_module.Queue[PendingMotionWindow | None] = queue_module.Queue(
            maxsize=max(1, args.append_queue_max_size),
        )
        self.append_queue: queue_module.Queue[PendingMotionWindow | None] = (
            queue_module.Queue(maxsize=max(1, args.append_queue_max_size))
        )
        self.guidance_delivery = GuidanceDeliveryWorker(
            args=args,
            live_session_id=live_session_id,
            practice_session_id=practice_session_id,
            guidance=guidance,
            analysis_metrics=analysis_metrics,
        )
        self.append_confirmations: deque[PendingMotionWindow] = deque()
        self.lock = threading.Lock()
        self.accepted_windows = 0
        self.rejected_windows = 0
        self.failed_windows = 0
        self.append_ack_deferred = 0
        self.append_ack_confirmed = 0
        self.append_rate_limit_retries = 0
        self.last_error: str | None = None
        self.drained = threading.Event()
        self.append_drained = threading.Event()
        self.drained.set()
        self.append_drained.set()
        self.matcher_thread = threading.Thread(
            target=self._run_matcher,
            name="motion-window-reference-matcher",
            daemon=True,
        )
        self.append_thread = threading.Thread(
            target=self._run_append,
            name="motion-window-appender",
            daemon=True,
        )
        self.thread = self.append_thread
        self.matcher_thread.start()
        self.append_thread.start()

    def enqueue(self, pending: PendingMotionWindow) -> bool:
        self.drained.clear()
        try:
            self.queue.put(pending, timeout=0.2)
            return True
        except queue_module.Full:
            with self.lock:
                self.failed_windows += 1
                self.last_error = "append_queue_full"
            emit(
                {
                    "event": "append_queue_backpressure",
                    "pending": self.queue.qsize(),
                    "window_id": pending.summary.get("window_id"),
                }
            )
            return False

    def stats(self) -> dict[str, Any]:
        with self.lock:
            match_pending = self.queue.qsize()
            append_pending = self.append_queue.qsize()
            confirmation_pending = len(self.append_confirmations)
            stats = {
                "accepted_windows": self.accepted_windows,
                "rejected_windows": self.rejected_windows,
                "failed_windows": self.failed_windows,
                "append_queue_pending": (
                    match_pending + append_pending + confirmation_pending
                ),
                "reference_match_queue_pending": match_pending,
                "append_api_queue_pending": append_pending,
                "append_ack_confirmation_pending": confirmation_pending,
                "append_ack_deferred": self.append_ack_deferred,
                "append_ack_confirmed": self.append_ack_confirmed,
                "append_rate_limit_retries": self.append_rate_limit_retries,
                "last_append_error": self.last_error,
            }
        stats.update(self.guidance_delivery.stats())
        return stats

    def close(self) -> None:
        close_timeout_sec = max(
            APPEND_SENDER_CLOSE_GRACE_SEC,
            float(getattr(self.args, "append_ack_recovery_max_sec", 0.0))
            + APPEND_SENDER_CLOSE_GRACE_SEC,
        )
        if not self.drained.wait(timeout=close_timeout_sec):
            self._record_dropped_windows(
                self._drain_queue(self.queue),
                event_name="reference_match_close_timeout",
            )
        self.queue.put(None, timeout=0.2)
        self.matcher_thread.join(timeout=5.0)
        if self.matcher_thread.is_alive():
            emit({"event": "reference_match_join_timeout"})

        if not self.append_drained.wait(timeout=close_timeout_sec):
            with self.lock:
                confirmation_dropped = len(self.append_confirmations)
                self.append_confirmations.clear()
            self._record_dropped_windows(
                self._drain_queue(self.append_queue) + confirmation_dropped,
                event_name="append_sender_close_timeout",
            )
        self.append_queue.put(None, timeout=0.2)
        self.append_thread.join(timeout=5.0)
        if self.append_thread.is_alive():
            emit({"event": "append_sender_join_timeout"})

        self.guidance_delivery.close(timeout_sec=close_timeout_sec)

    @staticmethod
    def _drain_queue(target_queue: queue_module.Queue[Any]) -> int:
        dropped = 0
        while True:
            try:
                item = target_queue.get_nowait()
            except queue_module.Empty:
                return dropped
            if item is not None:
                dropped += 1
            target_queue.task_done()

    def _record_dropped_windows(self, dropped: int, *, event_name: str) -> None:
        if dropped:
            with self.lock:
                self.failed_windows += dropped
                self.last_error = "append_close_timeout"
        emit({"event": event_name, "dropped_windows": dropped})

    def _run_matcher(self) -> None:
        while True:
            pending = self.queue.get()
            try:
                if pending is None:
                    return
                if self._annotate_reference(pending.summary):
                    self.append_drained.clear()
                    self.append_queue.put(pending)
            finally:
                self.queue.task_done()
                if self.queue.unfinished_tasks == 0:
                    self.drained.set()

    def _run_append(self) -> None:
        while True:
            from_fresh_queue = False
            try:
                pending = self.append_queue.get_nowait()
                from_fresh_queue = True
            except queue_module.Empty:
                pending = self._pop_due_confirmation()
            if pending is None:
                try:
                    pending = self.append_queue.get(timeout=0.25)
                    from_fresh_queue = True
                except queue_module.Empty:
                    continue
            try:
                if pending is None:
                    return
                self._append_pending(pending)
            finally:
                if from_fresh_queue:
                    self.append_queue.task_done()
                with self.lock:
                    confirmation_pending = bool(self.append_confirmations)
                if (
                    self.append_queue.unfinished_tasks == 0
                    and not confirmation_pending
                ):
                    self.append_drained.set()

    def _pop_due_confirmation(self) -> PendingMotionWindow | None:
        now = time.monotonic()
        with self.lock:
            if not self.append_confirmations:
                return None
            pending = self.append_confirmations[0]
            if pending.append_next_confirmation_monotonic > now:
                return None
            return self.append_confirmations.popleft()

    def _append_pending(self, pending: PendingMotionWindow) -> None:
        started_at = (
            self.analysis_metrics.started()
            if self.analysis_metrics is not None
            else None
        )
        rate_limit_started = time.monotonic()
        rate_limit_rounds = 0
        try:
            while True:
                try:
                    append_result = append_motion_window(
                        api_base=self.args.api_base,
                        summary=pending.summary,
                        received_at_ms=pending.received_at_ms,
                        api_timeout_sec=self.args.api_timeout_sec,
                        api_retry_count=(
                            1
                            if pending.append_confirmation_rounds > 0
                            else self.args.api_retry_count
                        ),
                        api_retry_backoff_sec=self.args.api_retry_backoff_sec,
                        append_owner_id=str(
                            getattr(self.args, "append_owner_id", "")
                        ),
                    )
                except Exception as exc:
                    if self._defer_append_confirmation(pending, exc):
                        return
                    with self.lock:
                        self.failed_windows += 1
                        self.last_error = str(exc)
                    emit(
                        {
                            "event": "append_window_failed",
                            "window_id": pending.summary.get("window_id"),
                            "error": str(exc),
                        }
                    )
                    return
                if append_result.get("accepted"):
                    break
                retry_delay = self._rate_limit_retry_delay(
                    append_result=append_result,
                    started_monotonic=rate_limit_started,
                    completed_rounds=rate_limit_rounds,
                )
                if retry_delay is None:
                    break
                rate_limit_rounds += 1
                with self.lock:
                    self.append_rate_limit_retries += 1
                emit(
                    {
                        "event": "append_window_rate_limit_deferred",
                        "window_id": pending.summary.get("window_id"),
                        "retry_round": rate_limit_rounds,
                        "retry_delay_sec": round(retry_delay, 3),
                    }
                )
                time.sleep(retry_delay)
                pending.received_at_ms = time.monotonic() * 1000.0
        finally:
            if started_at is not None and self.analysis_metrics is not None:
                self.analysis_metrics.record("append_api", started_at)

        if append_result.get("accepted"):
            with self.lock:
                self.accepted_windows += 1
                if pending.append_confirmation_rounds > 0:
                    self.append_ack_confirmed += 1
                self.last_error = None
            if self.guidance_enabled:
                self.guidance_delivery.enqueue(pending.summary, append_result)
            return

        with self.lock:
            self.rejected_windows += 1
            self.last_error = "append_not_accepted"
        emit(
            {
                "event": "append_window_rejected",
                "window_id": pending.summary.get("window_id"),
                "append_result": append_result,
            }
        )

    def _rate_limit_retry_delay(
        self,
        *,
        append_result: dict[str, Any],
        started_monotonic: float,
        completed_rounds: int,
    ) -> float | None:
        if append_result.get("reason") != "motion_window_rate_limited":
            return None
        if completed_rounds >= APPEND_ACK_CONFIRMATION_MAX_ROUNDS:
            return None
        now_monotonic = time.monotonic()
        maximum_recovery_sec = max(
            0.0,
            float(getattr(self.args, "append_ack_recovery_max_sec", 0.0)),
        )
        remaining_sec = maximum_recovery_sec - max(
            0.0,
            now_monotonic - started_monotonic,
        )
        if remaining_sec <= 0.0:
            return None
        next_allowed_at_ms = float(
            append_result.get("next_allowed_at_ms")
            or now_monotonic * 1000.0
        )
        requested_delay_sec = max(
            0.0,
            (next_allowed_at_ms - now_monotonic * 1000.0) / 1000.0,
        ) + APPEND_RATE_LIMIT_RETRY_PADDING_SEC
        if requested_delay_sec > remaining_sec:
            return None
        return requested_delay_sec

    def _defer_append_confirmation(
        self,
        pending: PendingMotionWindow,
        exc: Exception,
    ) -> bool:
        if not isinstance(exc, requests.RequestException):
            return False
        now = time.monotonic()
        schedule = schedule_append_confirmation(
            now_monotonic=now,
            first_failure_monotonic=pending.append_first_failure_monotonic,
            completed_rounds=pending.append_confirmation_rounds,
            maximum_rounds=APPEND_ACK_CONFIRMATION_MAX_ROUNDS,
            base_backoff_sec=float(
                getattr(self.args, "append_ack_recovery_backoff_sec", 0.0)
            ),
            maximum_recovery_sec=float(
                getattr(self.args, "append_ack_recovery_max_sec", 0.0)
            ),
        )
        if schedule is None:
            return False
        pending.append_confirmation_rounds = schedule.confirmation_round
        pending.append_first_failure_monotonic = (
            schedule.first_failure_monotonic
        )
        pending.append_next_confirmation_monotonic = (
            schedule.next_attempt_monotonic
        )
        with self.lock:
            self.append_ack_deferred += 1
            self.append_confirmations.append(pending)
            confirmation_pending = len(self.append_confirmations)
            self.last_error = f"append_ack_unconfirmed:{type(exc).__name__}"
        self.append_drained.clear()
        emit(
            {
                "event": "append_window_ack_deferred",
                "window_id": pending.summary.get("window_id"),
                "confirmation_round": pending.append_confirmation_rounds,
                "confirmation_pending": confirmation_pending,
                "retry_delay_sec": round(schedule.retry_delay_sec, 3),
                "error_type": type(exc).__name__,
            }
        )
        return True

    def _annotate_reference(self, summary: dict[str, Any]) -> bool:
        if self.reference_matcher is None:
            return True
        started_at = (
            self.analysis_metrics.started()
            if self.analysis_metrics is not None
            else None
        )
        try:
            self.reference_matcher.annotate(summary)
        except Exception as exc:
            with self.lock:
                self.failed_windows += 1
                self.last_error = f"reference_match_failed:{exc}"
            emit(
                {
                    "event": "reference_match_failed",
                    "window_id": summary.get("window_id"),
                    "error": str(exc),
                }
            )
            return False
        finally:
            if started_at is not None and self.analysis_metrics is not None:
                self.analysis_metrics.record("reference_match", started_at)
        if self.reference_alignment_observer is not None:
            try:
                self.reference_alignment_observer(summary)
            except Exception as exc:
                emit(
                    {
                        "event": "reference_alignment_observer_failed",
                        "window_id": summary.get("window_id"),
                        "error": str(exc),
                    }
                )
        return True
