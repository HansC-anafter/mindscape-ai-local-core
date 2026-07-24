from __future__ import annotations

import threading
import sys
import types


sys.modules.setdefault(
    "cv2",
    types.SimpleNamespace(
        CAP_FFMPEG=0,
        CAP_PROP_BUFFERSIZE=1,
        VideoCapture=lambda *_args, **_kwargs: None,
    ),
)

from scripts.rtmp_motion_publisher.capture import FfmpegRawFrameCapture
from scripts.rtmp_motion_publisher.capture_metrics import CaptureMetricsLedger
from scripts.rtmp_motion_publisher.reconnect import reconnect_stream
from scripts.rtmp_motion_publisher.session_policy import ReceiverSessionPolicy


class _StatsCapture:
    def __init__(self, stats: dict, *, opened: bool = False) -> None:
        self._stats = stats
        self._opened = opened
        self.released = False

    def stats(self) -> dict:
        return dict(self._stats)

    def isOpened(self) -> bool:
        return self._opened

    def release(self) -> None:
        self.released = True


def test_frame_pipe_idle_does_not_terminate_live_ffmpeg_reader(monkeypatch) -> None:
    class Process:
        returncode = None
        stdout = type("Stdout", (), {"fileno": lambda self: 7})()

        @staticmethod
        def poll():
            return None

    class Selector:
        calls = 0

        def select(self, _wait_sec):
            self.calls += 1
            return [] if self.calls == 1 else [object()]

    class Parser:
        frame = None

        def pop_frame(self):
            frame, self.frame = self.frame, None
            return frame

        def feed(self, _chunk):
            self.frame = b"jpeg-frame"

    capture = object.__new__(FfmpegRawFrameCapture)
    capture.process = Process()
    capture.selector = Selector()
    capture.read_timeout_sec = 1.0
    capture._jpeg_parser = Parser()
    capture._stop_reader = threading.Event()
    capture._pipe_bytes_read = 0
    capture._pipe_idle_timeout_count = 0
    capture._reader_error = None
    monkeypatch.setattr("rtmp_motion_publisher.capture.os.read", lambda *_args: b"chunk")

    assert capture._read_frame_bytes() == b"jpeg-frame"
    assert capture._pipe_idle_timeout_count == 1
    assert capture._pipe_bytes_read == 5
    assert capture._reader_error is None


def test_capture_metrics_accumulate_across_reconnect_generations() -> None:
    first = _StatsCapture(
        {
            "decoded_frames": 50,
            "overwritten_frames": 10,
            "pipe_bytes_read": 1000,
            "pipe_high_watermark_bytes": 200,
            "pipe_idle_timeout_count": 1,
            "reader_error": "ffmpeg_exit_1",
        }
    )
    second = _StatsCapture(
        {
            "decoded_frames": 30,
            "overwritten_frames": 4,
            "pipe_bytes_read": 600,
            "pipe_buffered_bytes": 12,
            "pipe_high_watermark_bytes": 180,
            "reader_error": None,
        }
    )
    ledger = CaptureMetricsLedger()

    ledger.close_generation(first)
    metrics = ledger.snapshot(second)

    assert metrics["decoded_frames"] == 80
    assert metrics["overwritten_frames"] == 14
    assert metrics["pipe_bytes_read"] == 1600
    assert metrics["pipe_high_watermark_bytes"] == 200
    assert metrics["pipe_buffered_bytes"] == 12
    assert metrics["pipe_idle_timeout_count"] == 1
    assert metrics["reader_error"] is None


def test_session_policy_uses_earliest_deadline_and_consecutive_retry_budget() -> None:
    args = type(
        "Args",
        (),
        {
            "duration_sec": 100.0,
            "session_expires_at_epoch": 1040.0,
            "stream_reconnect_max_attempts": 3,
        },
    )()
    policy = ReceiverSessionPolicy.from_args(
        args,
        started_at=10.0,
        now_epoch=1000.0,
    )

    assert policy.deadline_monotonic == 50.0
    assert policy.bounded_delay(10.0, now_monotonic=47.0) == 3.0
    assert policy.reconnect_block_reason(now_monotonic=20.0, outage_attempts=2) is None
    assert policy.reconnect_block_reason(
        now_monotonic=20.0,
        outage_attempts=3,
    ) == "reconnect_budget_exhausted"
    assert policy.reconnect_block_reason(
        now_monotonic=50.0,
        outage_attempts=0,
    ) == "session_deadline_reached"
    assert policy.active_elapsed_ms(started_at=10.0, now_monotonic=49.5) == 39_500.0
    assert policy.active_elapsed_ms(started_at=10.0, now_monotonic=50.0) is None
    assert policy.terminal_elapsed_ms(started_at=10.0, now_monotonic=55.0) == 40_000.0


def test_reconnect_loop_stops_at_outage_budget_and_keeps_metrics() -> None:
    args = type("Args", (), {"stream_reconnect_backoff_sec": 0.0})()
    policy = ReceiverSessionPolicy(
        deadline_monotonic=100.0,
        reconnect_max_attempts=2,
    )
    initial = _StatsCapture({"decoded_frames": 25, "pipe_bytes_read": 500})
    replacements: list[_StatsCapture] = []
    events: list[dict] = []
    states: list[tuple[str, dict]] = []
    ledger = CaptureMetricsLedger()

    def open_capture(_args):
        replacement = _StatsCapture({"decoded_frames": 0})
        replacements.append(replacement)
        return replacement

    result = reconnect_stream(
        args=args,
        capture=initial,
        reason="read_failed",
        started_at=0.0,
        total_attempts=4,
        policy=policy,
        capture_metrics=ledger,
        receiver_metrics=lambda attempts: {
            **ledger.snapshot(initial),
            "reconnect_attempts": attempts,
        },
        should_stop=lambda: False,
        open_capture=open_capture,
        emit_event=events.append,
        transition_state=lambda _args, state, **kwargs: states.append(
            (state, kwargs["metrics"])
        ),
        monotonic=lambda: 10.0,
        sleep=lambda _delay: None,
    )

    assert result.outcome == "failed"
    assert result.total_attempts == 6
    assert initial.released is True
    assert len(replacements) == 2
    assert all(capture.released for capture in replacements)
    assert states[0][1]["decoded_frames"] == 25
    assert states[0][1]["reconnect_attempts"] == 5
    assert events[-1]["reason"] == "reconnect_budget_exhausted"
