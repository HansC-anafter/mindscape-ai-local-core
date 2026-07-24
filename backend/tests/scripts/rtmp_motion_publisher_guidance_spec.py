from __future__ import annotations

import queue
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

import requests


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
from rtmp_motion_publisher.analysis_metrics import AnalysisStageMetrics  # noqa: E402
from rtmp_motion_publisher.windows import PendingMotionWindow  # noqa: E402


def _sender_args(*, guidance_enabled: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        disable_guidance_ws=not guidance_enabled,
        append_queue_max_size=4,
        api_base="http://api.test",
        api_timeout_sec=1,
        api_retry_count=2,
        api_retry_backoff_sec=0,
        append_ack_recovery_backoff_sec=0,
        append_ack_recovery_max_sec=1,
        append_owner_id="owner-1",
    )


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


def test_sender_orders_reference_annotation_before_append(monkeypatch) -> None:
    calls: list[str] = []

    class Matcher:
        def annotate(self, summary) -> None:
            calls.append("reference")
            summary["metadata"]["reference_alignment"] = {"chapter_id": "chapter-1"}

    def append_motion_window(**kwargs):
        calls.append("append")
        assert kwargs["summary"]["metadata"]["reference_alignment"] == {
            "chapter_id": "chapter-1"
        }
        return {"accepted": True, "motion_window_ref": "window-1"}

    monkeypatch.setattr(guidance, "append_motion_window", append_motion_window)
    metrics = AnalysisStageMetrics(clock=__import__("time").perf_counter)
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
        reference_matcher=Matcher(),
        analysis_metrics=metrics,
    )
    sender.enqueue(
        PendingMotionWindow(
            summary={
                "window_id": "window-1",
                "metadata": {},
                "confidence_stats": {"mean_confidence": 0.9},
                "findings": [],
            },
            received_at_ms=1,
        )
    )

    sender.close()

    assert calls == ["reference", "append"]
    assert sender.stats()["accepted_windows"] == 1
    assert metrics.snapshot()["stages"]["reference_match"]["count"] == 1


def test_sender_notifies_evidence_observer_after_reference_annotation(monkeypatch) -> None:
    observed: list[dict] = []

    class Matcher:
        def annotate(self, summary) -> None:
            summary.setdefault("metadata", {})["reference_alignment"] = {
                "reference_time_ms": 42_000,
            }

    monkeypatch.setattr(
        guidance,
        "append_motion_window",
        lambda **_kwargs: {"accepted": True, "motion_window_ref": "window-1"},
    )
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
        reference_matcher=Matcher(),
        reference_alignment_observer=lambda summary: observed.append(
            dict(summary["metadata"]["reference_alignment"])
        ),
    )
    sender.enqueue(
        PendingMotionWindow(
            summary={"window_id": "window-1", "metadata": {}},
            received_at_ms=1,
        )
    )

    sender.close()

    assert observed == [{"reference_time_ms": 42_000}]


def test_sender_stages_prevent_append_and_guidance_head_of_line_blocking(
    monkeypatch,
) -> None:
    matcher_second_seen = threading.Event()
    append_first_started = threading.Event()
    release_first_append = threading.Event()
    append_second_seen = threading.Event()
    guidance_first_started = threading.Event()
    release_first_guidance = threading.Event()

    class Matcher:
        def annotate(self, summary) -> None:
            summary["metadata"]["reference_alignment"] = {
                "chapter_id": summary["window_id"]
            }
            if summary["window_id"] == "window-2":
                matcher_second_seen.set()

    class FakeGuidance:
        def send(self, message):
            if message["event_id"] == "window-1:guidance":
                guidance_first_started.set()
                assert release_first_guidance.wait(timeout=2)
            return []

        def close(self) -> None:
            return None

    def append_motion_window(**kwargs):
        window_id = kwargs["summary"]["window_id"]
        if window_id == "window-1":
            append_first_started.set()
            assert release_first_append.wait(timeout=2)
        else:
            append_second_seen.set()
        return {"accepted": True, "motion_window_ref": window_id}

    monkeypatch.setattr(guidance, "append_motion_window", append_motion_window)
    metrics = AnalysisStageMetrics(clock=__import__("time").perf_counter)
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(guidance_enabled=True),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=FakeGuidance(),
        reference_matcher=Matcher(),
        analysis_metrics=metrics,
    )
    for index in (1, 2):
        assert sender.enqueue(
            PendingMotionWindow(
                summary={
                    "window_id": f"window-{index}",
                    "metadata": {},
                    "confidence_stats": {"mean_confidence": 0.9},
                    "findings": [],
                },
                received_at_ms=index,
            )
        )

    assert append_first_started.wait(timeout=1)
    assert matcher_second_seen.wait(timeout=1)
    release_first_append.set()
    assert guidance_first_started.wait(timeout=1)
    assert append_second_seen.wait(timeout=1)
    release_first_guidance.set()
    sender.close()

    stats = sender.stats()
    assert stats["accepted_windows"] == 2
    assert stats["failed_windows"] == 0
    assert stats["guidance_failures"] == 0
    assert stats["append_queue_pending"] == 0
    assert stats["guidance_queue_pending"] == 0
    stages = metrics.snapshot()["stages"]
    assert stages["reference_match"]["count"] == 2
    assert stages["append_api"]["count"] == 2
    assert stages["guidance_send"]["count"] == 2


def test_sender_reconciles_timed_out_append_after_fresh_windows(monkeypatch) -> None:
    calls: list[str] = []
    first_window_timed_out = False

    def append_motion_window(**kwargs):
        nonlocal first_window_timed_out
        window_id = kwargs["summary"]["window_id"]
        calls.append(window_id)
        if window_id == "window-1" and not first_window_timed_out:
            first_window_timed_out = True
            raise requests.ReadTimeout("ack unavailable")
        return {"accepted": True, "motion_window_ref": window_id}

    monkeypatch.setattr(guidance, "append_motion_window", append_motion_window)
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
    )
    for index in (1, 2):
        assert sender.enqueue(
            PendingMotionWindow(
                summary={"window_id": f"window-{index}"},
                received_at_ms=index,
            )
        )

    sender.close()

    assert calls == ["window-1", "window-2", "window-1"]
    stats = sender.stats()
    assert stats["accepted_windows"] == 2
    assert stats["failed_windows"] == 0
    assert stats["append_ack_deferred"] == 1
    assert stats["append_ack_confirmed"] == 1
    assert stats["append_ack_confirmation_pending"] == 0


def test_sender_does_not_reconcile_explicit_append_rejection(monkeypatch) -> None:
    calls = 0

    def append_motion_window(**_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("api_post_rejected:422:motion-windows:invalid")

    monkeypatch.setattr(guidance, "append_motion_window", append_motion_window)
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
    )
    assert sender.enqueue(
        PendingMotionWindow(summary={"window_id": "window-1"}, received_at_ms=1)
    )

    sender.close()

    assert calls == 1
    stats = sender.stats()
    assert stats["accepted_windows"] == 0
    assert stats["failed_windows"] == 1
    assert stats["append_ack_deferred"] == 0


def test_sender_defers_rate_limit_and_retries_same_window(monkeypatch) -> None:
    calls: list[tuple[str, float]] = []

    def append_motion_window(**kwargs):
        calls.append((kwargs["summary"]["window_id"], kwargs["received_at_ms"]))
        if len(calls) == 1:
            return {
                "accepted": False,
                "reason": "motion_window_rate_limited",
                "min_interval_ms": 500.0,
                "next_allowed_at_ms": 0.0,
            }
        return {"accepted": True, "motion_window_ref": "window-1"}

    monkeypatch.setattr(guidance, "append_motion_window", append_motion_window)
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
    )
    assert sender.enqueue(
        PendingMotionWindow(summary={"window_id": "window-1"}, received_at_ms=1)
    )

    sender.close()

    assert [window_id for window_id, _ in calls] == ["window-1", "window-1"]
    assert calls[1][1] > calls[0][1]
    stats = sender.stats()
    assert stats["accepted_windows"] == 1
    assert stats["rejected_windows"] == 0
    assert stats["failed_windows"] == 0
    assert stats["append_rate_limit_retries"] == 1


def test_sender_fails_after_bounded_append_confirmation_rounds(monkeypatch) -> None:
    calls = 0

    def append_motion_window(**_kwargs):
        nonlocal calls
        calls += 1
        raise requests.ReadTimeout("ack unavailable")

    monkeypatch.setattr(guidance, "append_motion_window", append_motion_window)
    sender = guidance.BackgroundMotionWindowSender(
        args=_sender_args(),
        live_session_id="live-1",
        practice_session_id="practice-1",
        guidance=None,
    )
    assert sender.enqueue(
        PendingMotionWindow(summary={"window_id": "window-1"}, received_at_ms=1)
    )

    sender.close()

    assert calls == 1 + guidance.APPEND_ACK_CONFIRMATION_MAX_ROUNDS
    stats = sender.stats()
    assert stats["accepted_windows"] == 0
    assert stats["failed_windows"] == 1
    assert stats["append_ack_deferred"] == guidance.APPEND_ACK_CONFIRMATION_MAX_ROUNDS
    assert stats["append_ack_confirmed"] == 0
