from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from rtmp_motion_publisher import guidance_delivery  # noqa: E402


def _args() -> SimpleNamespace:
    return SimpleNamespace(
        disable_guidance_ws=False,
        append_queue_max_size=8,
        api_base="http://api.test",
        workspace_id="workspace-1",
        meeting_id="meeting-1",
    )


def _summary(window_id: str) -> dict:
    return {
        "window_id": window_id,
        "confidence_stats": {"mean_confidence": 0.9},
        "findings": [],
        "metadata": {},
    }


def test_delivery_retries_same_window_in_order_after_socket_recovers(
    monkeypatch,
) -> None:
    delivered: list[str] = []
    emitted: list[dict] = []

    class FailedSocket:
        url = "ws://failed"

        def send(self, _message):
            raise ConnectionError("socket unavailable")

        def close(self) -> None:
            return None

    class RecoveredSocket:
        url = "ws://recovered"

        def __init__(self, **_kwargs) -> None:
            return None

        def read_events(self):
            return []

        def send(self, message):
            delivered.append(message["event_id"])
            return []

        def close(self) -> None:
            return None

    monkeypatch.setattr(guidance_delivery, "GuidanceSocket", RecoveredSocket)
    monkeypatch.setattr(guidance_delivery, "GUIDANCE_RETRY_BACKOFF_SECONDS", (0.01,))
    monkeypatch.setattr(guidance_delivery, "emit", emitted.append)
    worker = guidance_delivery.GuidanceDeliveryWorker(
        args=_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=FailedSocket(),
        analysis_metrics=None,
    )

    assert worker.enqueue(_summary("window-1"), {"motion_window_ref": "window-1"})
    assert worker.enqueue(_summary("window-2"), {"motion_window_ref": "window-2"})
    worker.close(timeout_sec=2.0)

    assert delivered == ["window-1:guidance", "window-2:guidance"]
    stats = worker.stats()
    assert stats["guidance_queue_pending"] == 0
    assert stats["guidance_reconnects"] == 1
    assert stats["guidance_delivery_retries"] == 1
    assert stats["guidance_failures"] == 0
    assert any(item["event"] == "guidance_delivery_deferred" for item in emitted)


def test_close_timeout_counts_inflight_and_pending_delivery_failures(
    monkeypatch,
) -> None:
    open_attempted = threading.Event()

    class UnavailableSocket:
        def __init__(self, **_kwargs) -> None:
            open_attempted.set()
            raise TimeoutError("meeting engine unavailable")

    monkeypatch.setattr(guidance_delivery, "GuidanceSocket", UnavailableSocket)
    monkeypatch.setattr(guidance_delivery, "GUIDANCE_RETRY_BACKOFF_SECONDS", (1.0,))
    worker = guidance_delivery.GuidanceDeliveryWorker(
        args=_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
        analysis_metrics=None,
    )

    assert worker.enqueue(_summary("window-1"), {"motion_window_ref": "window-1"})
    assert worker.enqueue(_summary("window-2"), {"motion_window_ref": "window-2"})
    assert open_attempted.wait(timeout=1.0)
    worker.close(timeout_sec=0.01)

    stats = worker.stats()
    assert stats["guidance_queue_pending"] == 0
    assert stats["guidance_failures"] == 2
    assert stats["last_guidance_error"] == "guidance_close_timeout"
