from argparse import Namespace
from pathlib import Path
import queue
import subprocess
import sys
import types

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

sys.modules.setdefault(
    "cv2",
    types.SimpleNamespace(
        CAP_FFMPEG=0,
        CAP_PROP_BUFFERSIZE=1,
        VideoCapture=lambda *_args, **_kwargs: None,
    ),
)
sys.modules.setdefault("mediapipe", types.SimpleNamespace())
sys.modules.setdefault(
    "websocket",
    types.SimpleNamespace(
        WebSocketTimeoutException=TimeoutError,
        WebSocketConnectionClosedException=ConnectionError,
        create_connection=lambda *_args, **_kwargs: None,
    ),
)

from rtmp_motion_publisher import app as publisher_app  # noqa: E402
from rtmp_motion_publisher.capture import FfmpegRawFrameCapture  # noqa: E402
from rtmp_motion_publisher.windows import PoseSample  # noqa: E402


class ClosedCapture:
    def __init__(self) -> None:
        self.released = False

    def isOpened(self) -> bool:
        return False

    def release(self) -> None:
        self.released = True


class StalledCapture:
    def __init__(self) -> None:
        self.released = False
        self.reads = 0

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, None]:
        self.reads += 1
        return False, None

    def release(self) -> None:
        self.released = True


def _args() -> Namespace:
    return Namespace(
        rtmp_url="rtmp://example.invalid/external-camera",
        api_base="http://localhost:8200",
        workspace_id="workspace-1",
        meeting_id="meeting-1",
        source_session_id="device_session_1",
        live_session_id=None,
        practice_session_id=None,
        duration_sec=0.0,
        sample_fps=1.0,
        window_sec=10.0,
        max_samples=30,
        status_every_sec=5.0,
        rollup_every_sec=60.0,
        expected_duration_ms=0.0,
        max_window_refs=100,
        model_asset_path=None,
        api_timeout_sec=1.0,
        rollup_api_timeout_sec=30.0,
        closeout_api_timeout_sec=30.0,
        api_retry_count=1,
        api_retry_backoff_sec=0.0,
        append_queue_max_size=8,
        capture_backend="ffmpeg",
        ffmpeg_bin="/usr/bin/ffmpeg",
        ffmpeg_realtime_input=False,
        frame_width=640,
        frame_height=360,
        avfoundation_framerate=60.0,
        stream_read_timeout_sec=1.0,
        stream_read_failure_threshold=3,
        stream_reconnect_backoff_sec=1.0,
        stream_reconnect_max_attempts=0,
        source_wait_timeout_sec=0.0,
        stream_gap_holdover_sec=0.0,
        stream_gap_holdover_confidence_cap=0.0,
        disable_guidance_ws=True,
        event_log_path="",
        motion_reference_profile_path="",
        materialize_practice_diary=False,
        practice_diary_reference_visual_evidence_path="",
    )


def test_ffmpeg_rtsps_capture_uses_tcp_timeout_and_tls_verification() -> None:
    capture = object.__new__(FfmpegRawFrameCapture)
    capture.rtmp_url = "rtsps://media.example.test:8322/live/path?token=secret"
    capture.read_timeout_sec = 7.5
    capture.avfoundation_framerate = 60.0

    assert capture._input_args() == [
        "-rtsp_transport",
        "tcp",
        "-timeout",
        "7500000",
        "-tls_verify",
        "1",
        "-i",
        capture.rtmp_url,
    ]


def test_ffmpeg_capture_uses_bounded_mjpeg_pipe(monkeypatch) -> None:
    launched: dict[str, object] = {}

    class Process:
        stdout = None

        @staticmethod
        def poll() -> int:
            return 0

    def popen(command, **kwargs):
        launched["command"] = command
        launched["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr("rtmp_motion_publisher.capture.subprocess.Popen", popen)
    capture = FfmpegRawFrameCapture(
        rtmp_url="rtsps://media.example.test/live/path",
        ffmpeg_bin="/usr/bin/ffmpeg",
        sample_fps=5.0,
        frame_width=640,
        frame_height=360,
        read_timeout_sec=10.0,
        avfoundation_framerate=60.0,
        ffmpeg_realtime_input=False,
    )

    command = launched["command"]
    assert isinstance(command, list)
    assert command[command.index("-c:v") + 1] == "mjpeg"
    assert command[command.index("-f") + 1] == "image2pipe"
    assert "rawvideo" not in command
    assert launched["kwargs"]["stderr"] is subprocess.DEVNULL
    capture.release()


def test_ffmpeg_capture_handoff_keeps_only_latest_frame() -> None:
    capture = object.__new__(FfmpegRawFrameCapture)
    capture._frames = queue.Queue(maxsize=1)
    capture._stop_reader = types.SimpleNamespace(is_set=lambda: False)
    capture._overwritten_frames = 0

    capture._replace_latest_frame(np.full((1, 1, 3), 1, dtype=np.uint8))
    capture._replace_latest_frame(np.full((1, 1, 3), 2, dtype=np.uint8))

    assert capture._frames.qsize() == 1
    assert capture._frames.get_nowait().tolist() == [[[2, 2, 2]]]
    assert capture._overwritten_frames == 1


def test_ffmpeg_capture_read_returns_buffered_frame_after_reader_finishes() -> None:
    capture = object.__new__(FfmpegRawFrameCapture)
    capture.process = object()
    capture.read_timeout_sec = 1.0
    capture._frames = queue.Queue(maxsize=1)
    capture._reader_done = types.SimpleNamespace(is_set=lambda: True)
    capture._frames.put_nowait(np.full((1, 1, 3), 7, dtype=np.uint8))

    ok, frame = capture.read()

    assert ok is True
    assert frame.tolist() == [[[7, 7, 7]]]


def test_public_reference_alignment_status_is_bounded() -> None:
    status = publisher_app._public_reference_alignment_status(
        {
            "metadata": {
                "reference_alignment": {
                    "chapter_id": "segment:010",
                    "reference_window_index": 233,
                    "score": 0.91,
                    "localization_score": 0.88,
                    "selection_mode": "ordered_local_prior",
                    "localization_ready": True,
                    "ordered_transition_supported": False,
                    "pending_transition_chapter_id": None,
                    "pending_transition_count": 0,
                    "pending_relock_chapter_id": "segment:009",
                    "pending_relock_count": 1,
                    "feature_deltas": [{"feature": "pose", "difference": 0.1}],
                    "reference_source_ref": "private-source",
                }
            }
        }
    )

    assert status == {
        "chapter_id": "segment:010",
        "reference_window_index": 233,
        "score": 0.91,
        "localization_score": 0.88,
        "localization_ready": True,
        "selection_mode": "ordered_local_prior",
        "ordered_transition_supported": False,
        "pending_transition_chapter_id": None,
        "pending_transition_count": 0,
        "pending_relock_chapter_id": "segment:009",
        "pending_relock_count": 1,
    }


def test_stream_open_failure_does_not_register_live_session(monkeypatch) -> None:
    captures: list[ClosedCapture] = []
    events: list[dict] = []
    registered: list[Namespace] = []
    args = _args()
    args.stream_reconnect_max_attempts = 1
    args.stream_reconnect_backoff_sec = 0.0

    monkeypatch.setattr(publisher_app, "parse_args", lambda: args)
    monkeypatch.setattr(
        publisher_app,
        "open_stream_capture",
        lambda _args: captures.append(ClosedCapture()) or captures[-1],
    )
    monkeypatch.setattr(publisher_app, "emit", events.append)
    monkeypatch.setattr(publisher_app, "transition_receiver_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        publisher_app,
        "register_live_session",
        lambda args: registered.append(args) or "lms_should_not_exist",
    )

    assert publisher_app.main() == 2
    assert len(captures) == 2
    assert all(capture.released for capture in captures)
    assert registered == []
    assert [event["event"] for event in events] == [
        "stream_open_failed",
        "stream_reconnect_started",
        "stream_open_failed",
        "stream_reconnect_give_up",
    ]


def test_initial_frame_failure_does_not_register_live_session(monkeypatch) -> None:
    captures: list[StalledCapture] = []
    events: list[dict] = []
    registered: list[Namespace] = []
    args = _args()
    args.stream_reconnect_max_attempts = 1
    args.stream_reconnect_backoff_sec = 0.0

    monkeypatch.setattr(publisher_app, "parse_args", lambda: args)
    monkeypatch.setattr(
        publisher_app,
        "open_stream_capture",
        lambda _args: captures.append(StalledCapture()) or captures[-1],
    )
    monkeypatch.setattr(publisher_app, "emit", events.append)
    monkeypatch.setattr(publisher_app, "transition_receiver_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        publisher_app,
        "register_live_session",
        lambda args: registered.append(args) or "lms_should_not_exist",
    )

    assert publisher_app.main() == 2
    assert len(captures) == 2
    assert all(capture.reads == 1 for capture in captures)
    assert all(capture.released for capture in captures)
    assert registered == []
    assert [event["event"] for event in events] == [
        "stream_open_failed",
        "stream_reconnect_started",
        "stream_open_failed",
        "stream_reconnect_give_up",
    ]


def test_initial_stream_wait_recovers_when_publisher_arrives(monkeypatch) -> None:
    stalled = StalledCapture()

    class ReadyCapture:
        def isOpened(self) -> bool:
            return True

        def read(self):
            return True, "first-frame"

        def release(self) -> None:
            return None

    ready = ReadyCapture()
    captures = iter((stalled, ready))
    args = _args()
    args.stream_reconnect_backoff_sec = 0.0
    events: list[dict] = []
    states: list[str] = []
    monkeypatch.setattr(publisher_app, "open_stream_capture", lambda _args: next(captures))
    monkeypatch.setattr(publisher_app, "emit", events.append)
    monkeypatch.setattr(
        publisher_app,
        "transition_receiver_state",
        lambda _args, state, **_kwargs: states.append(state),
    )

    acquired = publisher_app._acquire_initial_stream(
        args,
        should_stop=lambda: False,
        open_capture=publisher_app.open_stream_capture,
        emit_event=publisher_app.emit,
        transition_state=publisher_app.transition_receiver_state,
        monotonic=publisher_app.time.monotonic,
        sleep=publisher_app.time.sleep,
    )

    assert acquired == (ready, "first-frame", 1)
    assert stalled.released is True
    assert states == ["waiting_source"]
    assert [event["event"] for event in events] == [
        "stream_open_failed",
        "stream_reconnect_started",
    ]


def test_rollup_failure_is_reported_without_escaping_receiver(monkeypatch) -> None:
    events: list[dict] = []
    monkeypatch.setattr(publisher_app, "emit", events.append)
    monkeypatch.setattr(
        publisher_app,
        "emit_rollup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("slow rollup")),
    )

    result = publisher_app._try_emit_rollup(
        _args(),
        "motion-one",
        motion_reference_profile=None,
        failure_event="periodic_rollup_failed",
    )

    assert result is None
    assert events == [
        {
            "event": "periodic_rollup_failed",
            "live_session_id": "motion-one",
            "error_type": "TimeoutError",
            "error": "slow rollup",
        }
    ]


def test_receiver_flushes_partial_terminal_window_before_final_rollup(monkeypatch) -> None:
    class Capture:
        def isOpened(self) -> bool:
            return True

        def read(self):
            return True, object()

        def release(self) -> None:
            return None

    class Pose:
        def process(self, _frame, _timestamp_ms):
            return object()

        def close(self) -> None:
            return None

    class Sender:
        instance = None

        def __init__(self, **_kwargs) -> None:
            self.pending = []
            self.closed = False
            Sender.instance = self

        def enqueue(self, pending) -> bool:
            self.pending.append(pending)
            return True

        def close(self) -> None:
            self.closed = True

        def stats(self) -> dict:
            return {
                "accepted_windows": len(self.pending),
                "rejected_windows": 0,
                "failed_windows": 0,
                "append_queue_pending": 0,
                "last_append_error": None,
                "guidance_reconnects": 0,
                "guidance_failures": 0,
                "last_guidance_error": None,
            }

    class Evidence:
        def __init__(self, *_args) -> None:
            return None

        def capture_window(self, *_args) -> None:
            return None

        def finalize(self, _rollup):
            return None

        def cleanup_transient_frames(self) -> None:
            return None

    ticks = iter((0.0, 0.0, 0.6, 1.2, 1.8, 2.4, 3.0))
    args = _args()
    args.duration_sec = 1.5
    args.window_sec = 10.0
    args.disable_learner_visual_evidence = True
    args.learner_evidence_output_dir = ""
    args.learner_evidence_storage_dir = ""
    args.learner_evidence_max_windows = 10
    args.learner_evidence_jpeg_quality = 78
    events: list[dict] = []
    monkeypatch.setattr(publisher_app.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(publisher_app, "open_stream_capture", lambda _args: Capture())
    monkeypatch.setattr(publisher_app, "register_live_session", lambda _args: "motion-one")
    monkeypatch.setattr(publisher_app, "BackgroundMotionWindowSender", Sender)
    monkeypatch.setattr(
        publisher_app.PoseDetector,
        "create",
        lambda _path: Pose(),
    )
    monkeypatch.setattr(publisher_app.cv2, "COLOR_BGR2RGB", 1, raising=False)
    monkeypatch.setattr(publisher_app.cv2, "cvtColor", lambda frame, _code: frame, raising=False)
    monkeypatch.setattr(
        publisher_app,
        "pose_sample_from_result",
        lambda _result, timestamp_ms: PoseSample(
            timestamp_ms=timestamp_ms,
            confidence=0.9,
            visible_point_count=30,
            total_point_count=33,
        ),
    )
    monkeypatch.setattr(publisher_app, "LearnerVisualEvidenceRecorder", Evidence)
    monkeypatch.setattr(publisher_app, "start_stream_cost_tracking", lambda *_args: None)
    monkeypatch.setattr(
        publisher_app,
        "emit_rollup",
        lambda *_args, **_kwargs: {"motion_rollup_ref": "rollup-one"},
    )
    monkeypatch.setattr(publisher_app, "emit_yogacoach_closeout", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(publisher_app, "emit", events.append)

    assert publisher_app.run_receiver(args) == 0

    sender = Sender.instance
    assert sender is not None
    assert sender.closed is True
    assert len(sender.pending) == 1
    assert sender.pending[0].summary["ts_start_ms"] == 600.0
    assert sender.pending[0].summary["ts_end_ms"] == 1500.0
    assert any(event["event"] == "terminal_motion_window_flushed" for event in events)
