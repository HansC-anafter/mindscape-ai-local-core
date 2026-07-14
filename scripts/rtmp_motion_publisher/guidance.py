from __future__ import annotations

import argparse
import json
import queue as queue_module
import threading
from typing import Any
from urllib.parse import quote

import websocket

from .api_client import append_motion_window
from .events import emit
from .windows import PendingMotionWindow


APPEND_SENDER_CLOSE_TIMEOUT_SEC = 15.0


class GuidanceSocket:
    def __init__(
        self,
        *,
        api_base: str,
        workspace_id: str,
        meeting_id: str,
        practice_session_id: str,
        live_session_id: str,
    ) -> None:
        base = api_base.replace("https://", "wss://").replace("http://", "ws://").rstrip("/")
        self.url = (
            f"{base}/api/v1/workspaces/{quote(workspace_id, safe='')}"
            f"/meetings/{quote(meeting_id, safe='')}"
            f"/motion-guidance/{quote(practice_session_id, safe='')}/stream"
        )
        self.socket = websocket.create_connection(self.url, timeout=5)
        self.socket.settimeout(0.2)
        self.send(
            {
                "type": "session_start",
                "event_id": f"{practice_session_id}:session_start",
                "live_session_id": live_session_id,
            }
        )

    def send(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        self.socket.send(json.dumps(message))
        return self.read_events()

    def read_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            try:
                raw = self.socket.recv()
                if not raw:
                    break
                events.append(json.loads(raw))
            except TimeoutError:
                break
            except websocket.WebSocketTimeoutException:
                break
            except websocket.WebSocketConnectionClosedException:
                break
            except json.JSONDecodeError:
                break
        return events

    def close(self) -> None:
        try:
            try:
                self.send({"type": "session_close", "event_id": "rtmp_publisher:close"})
            except Exception as exc:
                emit({"event": "guidance_socket_close_failed", "error": str(exc)})
        finally:
            self.socket.close()


class BackgroundMotionWindowSender:
    def __init__(
        self,
        *,
        args: argparse.Namespace,
        live_session_id: str,
        practice_session_id: str,
        guidance: GuidanceSocket | None,
    ) -> None:
        self.args = args
        self.live_session_id = live_session_id
        self.practice_session_id = practice_session_id
        self.guidance_enabled = not args.disable_guidance_ws
        self.guidance = guidance
        self.queue: queue_module.Queue[PendingMotionWindow | None] = queue_module.Queue(
            maxsize=max(1, args.append_queue_max_size),
        )
        self.lock = threading.Lock()
        self.accepted_windows = 0
        self.rejected_windows = 0
        self.failed_windows = 0
        self.guidance_reconnects = 0
        self.guidance_failures = 0
        self.last_error: str | None = None
        self.last_guidance_error: str | None = None
        self.drained = threading.Event()
        self.drained.set()
        self.thread = threading.Thread(
            target=self._run,
            name="motion-window-sender",
            daemon=True,
        )
        self.thread.start()

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
            return {
                "accepted_windows": self.accepted_windows,
                "rejected_windows": self.rejected_windows,
                "failed_windows": self.failed_windows,
                "append_queue_pending": self.queue.qsize(),
                "last_append_error": self.last_error,
                "guidance_reconnects": self.guidance_reconnects,
                "guidance_failures": self.guidance_failures,
                "last_guidance_error": self.last_guidance_error,
            }

    def close(self) -> None:
        if not self.drained.wait(timeout=APPEND_SENDER_CLOSE_TIMEOUT_SEC):
            dropped = 0
            while True:
                try:
                    pending = self.queue.get_nowait()
                except queue_module.Empty:
                    break
                if pending is not None:
                    dropped += 1
                self.queue.task_done()
            if dropped:
                with self.lock:
                    self.failed_windows += dropped
                    self.last_error = "append_close_timeout"
            emit(
                {
                    "event": "append_sender_close_timeout",
                    "dropped_windows": dropped,
                }
            )
        self.queue.put(None, timeout=0.2)
        self.thread.join(timeout=5.0)
        if self.thread.is_alive():
            emit({"event": "append_sender_join_timeout"})
        if self.guidance is not None:
            self.guidance.close()
            self.guidance = None

    def _run(self) -> None:
        while True:
            pending = self.queue.get()
            try:
                if pending is None:
                    return
                self._send_pending(pending)
            finally:
                self.queue.task_done()
                if self.queue.unfinished_tasks == 0:
                    self.drained.set()

    def _send_pending(self, pending: PendingMotionWindow) -> None:
        try:
            append_result = append_motion_window(
                api_base=self.args.api_base,
                summary=pending.summary,
                received_at_ms=pending.received_at_ms,
                api_timeout_sec=self.args.api_timeout_sec,
                api_retry_count=self.args.api_retry_count,
                api_retry_backoff_sec=self.args.api_retry_backoff_sec,
                append_owner_id=str(getattr(self.args, "append_owner_id", "")),
            )
        except Exception as exc:
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
            with self.lock:
                self.accepted_windows += 1
                self.last_error = None
            self._send_guidance(pending.summary, append_result)
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

    def _send_guidance(
        self,
        summary: dict[str, Any],
        append_result: dict[str, Any],
    ) -> None:
        if self.guidance is None and not self._open_guidance_socket(
            event_name="guidance_socket_reopened",
        ):
            return
        guidance_message = {
            "type": "motion_window",
            "event_id": f"{summary['window_id']}:guidance",
            "live_session_id": self.live_session_id,
            "motion_window_ref": append_result.get("motion_window_ref"),
            "confidence": summary["confidence_stats"]["mean_confidence"],
            "findings": summary["findings"],
            "metadata": summary["metadata"],
        }
        try:
            for event in self.guidance.send(guidance_message):
                emit({"event": "guidance_event", "payload": event})
            with self.lock:
                self.last_guidance_error = None
        except Exception as exc:
            self._record_guidance_failure(exc)
            emit(
                {
                    "event": "guidance_send_failed",
                    "window_id": summary.get("window_id"),
                    "error": str(exc),
                }
            )
            self._close_guidance_socket()
            if not self._open_guidance_socket(event_name="guidance_socket_reopened"):
                return
            try:
                for event in self.guidance.send(guidance_message):
                    emit({"event": "guidance_event", "payload": event})
                with self.lock:
                    self.last_guidance_error = None
                emit(
                    {
                        "event": "guidance_send_recovered",
                        "window_id": summary.get("window_id"),
                    }
                )
            except Exception as retry_exc:
                self._record_guidance_failure(retry_exc)
                emit(
                    {
                        "event": "guidance_send_retry_failed",
                        "window_id": summary.get("window_id"),
                        "error": str(retry_exc),
                    }
                )
                self._close_guidance_socket()

    def _open_guidance_socket(self, *, event_name: str) -> bool:
        if not self.guidance_enabled:
            return False
        try:
            self.guidance = GuidanceSocket(
                api_base=self.args.api_base,
                workspace_id=self.args.workspace_id,
                meeting_id=self.args.meeting_id,
                practice_session_id=self.practice_session_id,
                live_session_id=self.live_session_id,
            )
            with self.lock:
                self.guidance_reconnects += 1
                self.last_guidance_error = None
            emit({"event": event_name, "url": self.guidance.url})
            for event in self.guidance.read_events():
                emit({"event": "guidance_event", "payload": event})
            return True
        except Exception as exc:
            self.guidance = None
            self._record_guidance_failure(exc)
            emit({"event": "guidance_socket_reopen_failed", "error": str(exc)})
            return False

    def _close_guidance_socket(self) -> None:
        if self.guidance is None:
            return
        try:
            self.guidance.close()
        except Exception as exc:
            emit({"event": "guidance_socket_close_failed", "error": str(exc)})
        finally:
            self.guidance = None

    def _record_guidance_failure(self, exc: Exception) -> None:
        with self.lock:
            self.guidance_failures += 1
            self.last_guidance_error = str(exc)
