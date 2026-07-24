from __future__ import annotations

import argparse
import queue
import threading
from dataclasses import dataclass
from typing import Any

from .analysis_metrics import AnalysisStageMetrics
from .events import emit
from .guidance_socket import GuidanceSocket


GUIDANCE_RETRY_BACKOFF_SECONDS = (0.5, 1.5, 5.0)


@dataclass(frozen=True)
class GuidanceDelivery:
    summary: dict[str, Any]
    append_result: dict[str, Any]


class GuidanceDeliveryWorker:
    """Deliver accepted motion windows in order across transient socket outages."""

    def __init__(
        self,
        *,
        args: argparse.Namespace,
        live_session_id: str,
        practice_session_id: str,
        guidance: GuidanceSocket | None,
        analysis_metrics: AnalysisStageMetrics | None,
    ) -> None:
        self.args = args
        self.live_session_id = live_session_id
        self.practice_session_id = practice_session_id
        self.guidance_enabled = not args.disable_guidance_ws
        self.guidance = guidance
        self.analysis_metrics = analysis_metrics
        self.queue: queue.Queue[GuidanceDelivery | None] = queue.Queue(
            maxsize=max(1, args.append_queue_max_size),
        )
        self.lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.drained = threading.Event()
        self.drained.set()
        self.inflight = 0
        self.reconnects = 0
        self.delivery_retries = 0
        self.failures = 0
        self.last_error: str | None = None
        self.thread = threading.Thread(
            target=self._run,
            name="motion-window-guidance",
            daemon=True,
        )
        self.thread.start()

    def enqueue(
        self,
        summary: dict[str, Any],
        append_result: dict[str, Any],
    ) -> bool:
        if not self.guidance_enabled:
            return True
        try:
            self.queue.put(
                GuidanceDelivery(summary=summary, append_result=append_result),
                timeout=0.2,
            )
            self.drained.clear()
            return True
        except queue.Full:
            with self.lock:
                self.failures += 1
                self.last_error = "guidance_queue_full"
            emit(
                {
                    "event": "guidance_queue_backpressure",
                    "pending": self.queue.qsize(),
                    "window_id": summary.get("window_id"),
                }
            )
            return False

    def stats(self) -> dict[str, Any]:
        with self.lock:
            return {
                "guidance_queue_pending": self.queue.qsize() + self.inflight,
                "guidance_reconnects": self.reconnects,
                "guidance_delivery_retries": self.delivery_retries,
                "guidance_failures": self.failures,
                "last_guidance_error": self.last_error,
            }

    def close(self, *, timeout_sec: float) -> None:
        if not self.drained.wait(timeout=timeout_sec):
            self.stop_requested.set()
            dropped = self._drain_pending()
            if dropped:
                with self.lock:
                    self.failures += dropped
                    self.last_error = "guidance_close_timeout"
            emit(
                {
                    "event": "guidance_sender_close_timeout",
                    "dropped_windows": dropped,
                }
            )
        self.queue.put(None, timeout=0.2)
        self.thread.join(timeout=7.0)
        if self.thread.is_alive():
            emit({"event": "guidance_sender_join_timeout"})
        self._close_socket()

    def _run(self) -> None:
        while True:
            delivery = self.queue.get()
            try:
                if delivery is None:
                    return
                with self.lock:
                    self.inflight = 1
                if not self._deliver_until_terminal(delivery):
                    with self.lock:
                        self.failures += 1
                        self.last_error = "guidance_close_timeout"
                    emit(
                        {
                            "event": "guidance_delivery_terminal_failure",
                            "window_id": delivery.summary.get("window_id"),
                        }
                    )
            finally:
                with self.lock:
                    self.inflight = 0
                self.queue.task_done()
                if self.queue.unfinished_tasks == 0:
                    self.drained.set()

    def _deliver_until_terminal(self, delivery: GuidanceDelivery) -> bool:
        retry_index = 0
        while not self.stop_requested.is_set():
            started_at = (
                self.analysis_metrics.started()
                if self.analysis_metrics is not None
                else None
            )
            try:
                if self._deliver_once(delivery):
                    with self.lock:
                        self.last_error = None
                    return True
            finally:
                if started_at is not None and self.analysis_metrics is not None:
                    self.analysis_metrics.record("guidance_send", started_at)
            delay_sec = GUIDANCE_RETRY_BACKOFF_SECONDS[
                min(retry_index, len(GUIDANCE_RETRY_BACKOFF_SECONDS) - 1)
            ]
            retry_index += 1
            with self.lock:
                self.delivery_retries += 1
                retry_count = self.delivery_retries
            emit(
                {
                    "event": "guidance_delivery_deferred",
                    "window_id": delivery.summary.get("window_id"),
                    "delivery_retry_count": retry_count,
                    "retry_delay_sec": delay_sec,
                }
            )
            if self.stop_requested.wait(timeout=delay_sec):
                break
        return False

    def _deliver_once(self, delivery: GuidanceDelivery) -> bool:
        if self.guidance is None and not self._open_socket():
            return False
        message = {
            "type": "motion_window",
            "event_id": f"{delivery.summary['window_id']}:guidance",
            "live_session_id": self.live_session_id,
            "motion_window_ref": delivery.append_result.get("motion_window_ref"),
            "confidence": delivery.summary["confidence_stats"]["mean_confidence"],
            "findings": delivery.summary["findings"],
            "metadata": delivery.summary["metadata"],
        }
        try:
            for event in self.guidance.send(message):
                emit({"event": "guidance_event", "payload": event})
            return True
        except Exception as exc:
            self._record_attempt_error(exc)
            emit(
                {
                    "event": "guidance_send_failed",
                    "window_id": delivery.summary.get("window_id"),
                    "error": str(exc),
                }
            )
            self._close_socket()
            return False

    def _open_socket(self) -> bool:
        try:
            self.guidance = GuidanceSocket(
                api_base=self.args.api_base,
                workspace_id=self.args.workspace_id,
                meeting_id=self.args.meeting_id,
                practice_session_id=self.practice_session_id,
                live_session_id=self.live_session_id,
            )
            with self.lock:
                self.reconnects += 1
                self.last_error = None
            emit({"event": "guidance_socket_reopened", "url": self.guidance.url})
            for event in self.guidance.read_events():
                emit({"event": "guidance_event", "payload": event})
            return True
        except Exception as exc:
            self.guidance = None
            self._record_attempt_error(exc)
            emit({"event": "guidance_socket_reopen_failed", "error": str(exc)})
            return False

    def _record_attempt_error(self, exc: Exception) -> None:
        with self.lock:
            self.last_error = str(exc)

    def _close_socket(self) -> None:
        if self.guidance is None:
            return
        try:
            self.guidance.close()
        except Exception as exc:
            emit({"event": "guidance_socket_close_failed", "error": str(exc)})
        finally:
            self.guidance = None

    def _drain_pending(self) -> int:
        dropped = 0
        while True:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                return dropped
            if item is not None:
                dropped += 1
            self.queue.task_done()


__all__ = ["GuidanceDeliveryWorker"]
