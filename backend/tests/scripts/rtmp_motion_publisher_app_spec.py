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
from rtmp_motion_publisher.capture import (  # noqa: E402
    FfmpegRawFrameCapture,
    RETAINED_VIDEO_FINALIZE_TIMEOUT_SEC,
)


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
        source_wait_max_attempts=0,
        session_expires_at_epoch=0.0,
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


def test_ffmpeg_capture_retains_one_mp4_without_opening_a_second_source_reader(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
    retained_path = tmp_path / "learner-capture-part-000.mp4"
    capture = FfmpegRawFrameCapture(
        rtmp_url="rtsps://media.example.test/live/path",
        ffmpeg_bin="/usr/bin/ffmpeg",
        sample_fps=5.0,
        frame_width=640,
        frame_height=360,
        read_timeout_sec=10.0,
        avfoundation_framerate=60.0,
        ffmpeg_realtime_input=False,
        retained_video_path=retained_path,
    )

    command = launched["command"]
    assert isinstance(command, list)
    assert command.count("-i") == 1
    assert command.count("-map") == 2
    assert [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "-c:v"
    ] == ["copy", "mjpeg"]
    retained_movflags_index = command.index("-movflags")
    assert command[retained_movflags_index + 1] == "+faststart"
    assert "empty_moov" not in command
    assert "frag_keyframe" not in command
    assert str(retained_path) in command
    assert command[-1] == "pipe:1"
    capture.release()


def test_retained_capture_drains_frames_until_ffmpeg_finalizes_mp4() -> None:
    events: list[object] = []

    class StopReader:
        stopped = False

        def set(self) -> None:
            self.stopped = True
            events.append("reader_stopped")

    stop_reader = StopReader()

    class Process:
        returncode = 0

        @staticmethod
        def poll() -> None:
            return None

        @staticmethod
        def terminate() -> None:
            events.append("terminate")

        @staticmethod
        def wait(*, timeout: float) -> int:
            assert stop_reader.stopped is False
            events.append(("wait", timeout))
            return 0

        @staticmethod
        def kill() -> None:
            raise AssertionError("graceful retained-video finalization must not kill")

    capture = object.__new__(FfmpegRawFrameCapture)
    capture.process = Process()
    capture.retained_video_path = Path("learner-capture-part-000.mp4")
    capture._stop_reader = stop_reader
    capture._reader_thread = None
    capture.selector = None

    capture.release()

    assert events == [
        "terminate",
        ("wait", RETAINED_VIDEO_FINALIZE_TIMEOUT_SEC),
        "reader_stopped",
    ]
    assert capture.process is None


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
    args.source_wait_max_attempts = 1
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
        "source_wait_retry_started",
        "stream_open_failed",
        "source_wait_expired",
    ]


def test_initial_frame_failure_does_not_register_live_session(monkeypatch) -> None:
    captures: list[StalledCapture] = []
    events: list[dict] = []
    registered: list[Namespace] = []
    args = _args()
    args.source_wait_max_attempts = 1
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
        "source_wait_retry_started",
        "stream_open_failed",
        "source_wait_expired",
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
        "source_wait_retry_started",
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
