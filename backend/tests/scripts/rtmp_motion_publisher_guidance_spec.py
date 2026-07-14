from __future__ import annotations

import queue
import sys
import threading
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

sys.modules.setdefault(
    "websocket",
    types.SimpleNamespace(
        WebSocketTimeoutException=TimeoutError,
        WebSocketConnectionClosedException=ConnectionError,
    ),
)

from rtmp_motion_publisher import guidance  # noqa: E402
from rtmp_motion_publisher.windows import PendingMotionWindow  # noqa: E402


def test_full_append_queue_fails_window_without_blocking(monkeypatch) -> None:
    sender = object.__new__(guidance.BackgroundMotionWindowSender)
    sender.queue = queue.Queue(maxsize=1)
    sender.queue.put(PendingMotionWindow(summary={"window_id": "first"}, received_at_ms=1))
    sender.lock = threading.Lock()
    sender.failed_windows = 0
    sender.last_error = None
    sender.drained = threading.Event()
    events: list[dict] = []
    monkeypatch.setattr(guidance, "emit", events.append)

    accepted = sender.enqueue(
        PendingMotionWindow(summary={"window_id": "second"}, received_at_ms=2)
    )

    assert accepted is False
    assert sender.queue.qsize() == 1
    assert sender.failed_windows == 1
    assert sender.last_error == "append_queue_full"
    assert events == [
        {
            "event": "append_queue_backpressure",
            "pending": 1,
            "window_id": "second",
        }
    ]
