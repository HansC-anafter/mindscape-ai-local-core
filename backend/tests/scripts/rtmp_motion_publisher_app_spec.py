from argparse import Namespace
from pathlib import Path
import sys
import types


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
    capture = ClosedCapture()
    events: list[dict] = []
    registered: list[Namespace] = []

    monkeypatch.setattr(publisher_app, "parse_args", _args)
    monkeypatch.setattr(publisher_app, "open_stream_capture", lambda _args: capture)
    monkeypatch.setattr(publisher_app, "emit", events.append)
    monkeypatch.setattr(
        publisher_app,
        "register_live_session",
        lambda args: registered.append(args) or "lms_should_not_exist",
    )

    assert publisher_app.main() == 2
    assert capture.released is True
    assert registered == []
    assert events == [
        {
            "event": "stream_open_failed",
            "input_uri": "rtmp://example.invalid/external-camera",
        }
    ]


def test_initial_frame_failure_does_not_register_live_session(monkeypatch) -> None:
    capture = StalledCapture()
    events: list[dict] = []
    registered: list[Namespace] = []

    monkeypatch.setattr(publisher_app, "parse_args", _args)
    monkeypatch.setattr(publisher_app, "open_stream_capture", lambda _args: capture)
    monkeypatch.setattr(publisher_app, "emit", events.append)
    monkeypatch.setattr(
        publisher_app,
        "register_live_session",
        lambda args: registered.append(args) or "lms_should_not_exist",
    )

    assert publisher_app.main() == 2
    assert capture.reads == 1
    assert capture.released is True
    assert registered == []
    assert events == [
        {
            "event": "stream_open_failed",
            "input_uri": "rtmp://example.invalid/external-camera",
            "reason": "initial_frame_unavailable",
        }
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
