from __future__ import annotations

import json
import os
import queue
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import requests

from .events import emit


_STABLE_REASON = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_REPORTER_QUEUE_SIZE = 8
_METRIC_COUNTERS = (
    "attempted_windows",
    "accepted_windows",
    "rejected_windows",
    "failed_windows",
    "append_queue_pending",
    "reconnect_attempts",
    "decoded_frames",
    "overwritten_frames",
    "decode_errors",
    "pipe_bytes_read",
    "pipe_buffered_bytes",
    "pipe_high_watermark_bytes",
    "pipe_discarded_bytes",
    "pipe_overflow_count",
)


def _bounded_metrics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(value or {})
    metrics: dict[str, Any] = {
        key: max(0, int(source.get(key) or 0)) for key in _METRIC_COUNTERS
    }
    last_window_end_ms = source.get("last_window_end_ms")
    if isinstance(last_window_end_ms, (int, float)) and not isinstance(
        last_window_end_ms,
        bool,
    ):
        metrics["last_window_end_ms"] = max(0.0, float(last_window_end_ms))
    chapter_id = str(source.get("reference_chapter_id") or "").strip()
    if chapter_id:
        metrics["reference_chapter_id"] = chapter_id[:160]
    localization_ready = source.get("reference_localization_ready")
    if isinstance(localization_ready, bool):
        metrics["reference_localization_ready"] = localization_ready
    return metrics


class _ReceiverStateEventReporter:
    def __init__(self) -> None:
        self.queue: queue.Queue[tuple[str, dict[str, Any], str] | None] = queue.Queue(
            maxsize=_REPORTER_QUEUE_SIZE
        )
        self.thread = threading.Thread(
            target=self._run,
            name="receiver-state-event-reporter",
            daemon=True,
        )
        self.thread.start()

    def submit(self, url: str, payload: dict[str, Any], token: str) -> None:
        try:
            self.queue.put_nowait((url, payload, token))
            return
        except queue.Full:
            pass
        try:
            self.queue.get_nowait()
            self.queue.task_done()
        except queue.Empty:
            return
        try:
            self.queue.put_nowait((url, payload, token))
        except queue.Full:
            emit({"event": "receiver_state_event_queue_full"})

    def close(self) -> None:
        while True:
            try:
                self.queue.put_nowait(None)
                break
            except queue.Full:
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except queue.Empty:
                    break
        self.thread.join(timeout=5.0)
        if self.thread.is_alive():
            emit({"event": "receiver_state_event_reporter_close_timeout"})

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                url, payload, token = item
                try:
                    response = requests.post(
                        url,
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=3.0,
                    )
                    if response.status_code >= 400:
                        emit(
                            {
                                "event": "receiver_state_event_rejected",
                                "status_code": response.status_code,
                                "state": payload.get("state"),
                            }
                        )
                except requests.RequestException as exc:
                    emit(
                        {
                            "event": "receiver_state_event_failed",
                            "error_type": type(exc).__name__,
                            "state": payload.get("state"),
                        }
                    )
            finally:
                self.queue.task_done()


_reporter: _ReceiverStateEventReporter | None = None
_reporter_lock = threading.Lock()


def _event_target(args: Any) -> tuple[str, str] | None:
    api_base = str(getattr(args, "api_base", "") or "").rstrip("/")
    workspace_id = str(getattr(args, "workspace_id", "") or "").strip()
    device_session_id = str(
        getattr(args, "source_session_id", "") or ""
    ).strip()
    media_session_id = str(getattr(args, "media_session_id", "") or "").strip()
    token = str(getattr(args, "append_owner_id", "") or "").strip()
    if not all((api_base, workspace_id, device_session_id, media_session_id, token)):
        return None
    url = (
        f"{api_base}/api/v1/workspaces/{quote(workspace_id, safe='')}"
        f"/device-bindings/{quote(device_session_id, safe='')}"
        f"/media-sessions/{quote(media_session_id, safe='')}/receiver/events"
    )
    return url, token


def _submit_event(args: Any, payload: dict[str, Any]) -> None:
    target = _event_target(args)
    if target is None:
        return
    global _reporter
    with _reporter_lock:
        if _reporter is None:
            _reporter = _ReceiverStateEventReporter()
        reporter = _reporter
    reporter.submit(target[0], payload, target[1])


def close_receiver_state_reporter() -> None:
    global _reporter
    with _reporter_lock:
        reporter = _reporter
        _reporter = None
    if reporter is not None:
        reporter.close()


def safe_receiver_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    if isinstance(exc, ValueError) and _STABLE_REASON.fullmatch(message):
        return message
    if isinstance(exc, OSError):
        errno = exc.errno if isinstance(exc.errno, int) else "unknown"
        return f"live_media_receiver_os_error_{errno}"
    return "live_media_receiver_runtime_failed"


def transition_receiver_state(
    args: Any,
    state: str,
    *,
    reason: str | None = None,
    metrics: Mapping[str, Any] | None = None,
) -> None:
    raw_path = str(getattr(args, "receiver_state_path", "") or "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "schema_version": "live_media_receiver_state.v1",
        "workspace_id": str(args.workspace_id),
        "media_session_id": str(getattr(args, "media_session_id", "")),
        "receiver_identity": str(getattr(args, "receiver_identity", "")),
        "pid": os.getpid(),
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": _bounded_metrics(metrics),
    }
    if reason:
        payload["reason"] = reason[:500]
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)
    event_payload = {
        "schema_version": "live_media_receiver_event.v1",
        "state": state,
        "updated_at": payload["updated_at"],
        "metrics": payload["metrics"],
    }
    if reason:
        event_payload["reason"] = reason[:128]
    _submit_event(args, event_payload)


__all__ = [
    "close_receiver_state_reporter",
    "safe_receiver_failure_reason",
    "transition_receiver_state",
]
