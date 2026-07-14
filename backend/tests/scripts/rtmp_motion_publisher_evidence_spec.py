from argparse import Namespace
from pathlib import Path
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
        IMWRITE_JPEG_QUALITY=1,
        INTER_AREA=2,
    ),
)

from rtmp_motion_publisher import api_client, evidence  # noqa: E402
from rtmp_motion_publisher.closeout import _input_asset_kind, _source_mode  # noqa: E402
from rtmp_motion_publisher.receiver_state import (  # noqa: E402
    safe_receiver_failure_reason,
)


class FakeCV2:
    IMWRITE_JPEG_QUALITY = 1
    INTER_AREA = 2

    def __init__(self) -> None:
        self.images: dict[str, np.ndarray] = {}

    def imwrite(self, path: str, image: np.ndarray, _params: list[int]) -> bool:
        self.images[path] = image.copy()
        Path(path).write_bytes(b"bounded-test-jpeg")
        return True

    def imread(self, path: str) -> np.ndarray | None:
        image = self.images.get(path)
        return image.copy() if image is not None else None

    def resize(
        self,
        _image: np.ndarray,
        size: tuple[int, int],
        *,
        interpolation: int,
    ) -> np.ndarray:
        assert interpolation == self.INTER_AREA
        width, height = size
        return np.zeros((height, width, 3), dtype=np.uint8)


def _args(tmp_path: Path, input_uri: str) -> Namespace:
    return Namespace(
        rtmp_url=input_uri,
        api_base="http://localhost:8200",
        workspace_id="workspace-1",
        meeting_id="meeting-1",
        source_session_id="device_session_capture_1",
        source_kind="phone_camera",
        transport_kind="rtsps" if input_uri.startswith("rtsps://") else "local_rtmp",
        media_session_id="media-one",
        receiver_identity="receiver-one",
        api_timeout_sec=1.0,
        api_retry_count=1,
        api_retry_backoff_sec=0.0,
        disable_learner_visual_evidence=False,
        learner_evidence_output_dir=str(tmp_path / "host-evidence"),
        learner_evidence_storage_dir="/app/backend/data/test-evidence",
        learner_evidence_max_windows=10,
        learner_evidence_jpeg_quality=78,
    )


def test_direct_file_replay_cannot_emit_learner_capture_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[dict] = []
    monkeypatch.setattr(evidence, "emit", events.append)
    recorder = evidence.LearnerVisualEvidenceRecorder(
        _args(tmp_path, "/private/tmp/reference.m4s"),
        "lms-file-replay",
    )

    result = recorder.finalize({})

    assert recorder.enabled is False
    assert result == {
        "status": "unavailable",
        "reason": "input_is_not_live_capture",
        "assets": [],
    }
    assert events[0]["reason"] == "input_is_not_live_capture"


def test_closeout_source_mode_distinguishes_live_capture_from_file_replay(
    tmp_path: Path,
) -> None:
    replay_path = tmp_path / "reference-video.m4s"
    replay_path.write_bytes(b"fixture")

    assert _input_asset_kind(str(replay_path)) == "file_replay"
    assert _source_mode(_input_asset_kind(str(replay_path))) == "reference_replay"
    assert _input_asset_kind("rtmp://example.test/live") == "rtmp_capture"
    assert _source_mode(_input_asset_kind("rtmp://example.test/live")) == "live_capture"
    assert _input_asset_kind("rtsps://media.test:8322/live") == "relay_capture"
    assert _source_mode(_input_asset_kind("rtsps://media.test:8322/live")) == "live_capture"
    assert _input_asset_kind(
        "rtsps://media.test:8322/live?token=" + ("credential" * 80)
    ) == "relay_capture"


def test_receiver_failure_reason_never_persists_source_credentials() -> None:
    error = OSError(
        63,
        "File name too long",
        "rtsps://media.test/live?token=jwt-credential",
    )

    reason = safe_receiver_failure_reason(error)

    assert reason == "live_media_receiver_os_error_63"
    assert "jwt-credential" not in reason
    assert safe_receiver_failure_reason(ValueError("receiver_descriptor_expired")) == (
        "receiver_descriptor_expired"
    )


def test_persisted_evidence_removes_live_media_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    requests: list[dict] = []
    fake_cv2 = FakeCV2()
    monkeypatch.setattr(evidence, "cv2", fake_cv2)
    monkeypatch.setattr(evidence, "emit", lambda _event: None)
    monkeypatch.setattr(
        evidence,
        "api_post",
        lambda _base, _path, payload, **_kwargs: requests.append(payload)
        or {"id": "learner-contact-sheet-artifact"},
    )
    recorder = evidence.LearnerVisualEvidenceRecorder(
        _args(
            tmp_path,
            "rtsps://receiver:basic-password@media.test:8322/live/path?token=jwt-credential",
        ),
        "lms-secret-redaction",
    )
    recorder.capture_window(
        np.zeros((360, 640, 3), dtype=np.uint8),
        {
            "window_id": "lms-secret-redaction:motion-window:0:0",
            "ts_start_ms": 0,
            "ts_end_ms": 2000,
        },
    )
    result = recorder.finalize(
        {
            "summary": {
                "metadata": {
                    "reference_segments": [
                        {"segment_start_ms": 0, "segment_end_ms": 2000}
                    ]
                }
            }
        }
    )

    assert result["status"] == "ready"
    assert requests[0]["metadata"]["capture_input_uri"] == (
        "rtsps://media.test:8322/live/path"
    )
    assert requests[0]["metadata"]["capture_input_kind"] == "remote_webrtc"
    assert requests[0]["metadata"]["media_session_id"] == "media-one"
    assert requests[0]["metadata"]["receiver_identity"] == "receiver-one"
    assert "basic-password" not in str(requests[0])
    assert "jwt-credential" not in str(requests[0])


def test_rtmp_capture_emits_session_bound_adaptive_chapter_frames(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_cv2 = FakeCV2()
    requests: list[dict] = []
    monkeypatch.setattr(evidence, "cv2", fake_cv2)
    monkeypatch.setattr(evidence, "emit", lambda _event: None)
    monkeypatch.setattr(
        evidence,
        "api_post",
        lambda _base, _path, payload, **_kwargs: requests.append(payload)
        or {"id": "learner-contact-sheet-artifact"},
    )
    recorder = evidence.LearnerVisualEvidenceRecorder(
        _args(tmp_path, "rtmp://34.80.219.221:1935/external-camera"),
        "lms-live-capture",
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    recorder.capture_window(
        frame,
        {
            "window_id": "lms-live-capture:rtmp-window:0:0",
            "ts_start_ms": 0,
            "ts_end_ms": 2000,
        },
    )
    recorder.capture_window(
        frame,
        {
            "window_id": "lms-live-capture:rtmp-window:2000:1",
            "ts_start_ms": 2000,
            "ts_end_ms": 4000,
        },
    )
    result = recorder.finalize(
        {
            "summary": {
                "metadata": {
                    "reference_segments": [
                        {
                            "segment_id": "lms-live-capture:segment:001",
                            "segment_start_ms": 0,
                            "segment_end_ms": 1900,
                        },
                        {
                            "segment_id": "lms-live-capture:segment:002",
                            "segment_start_ms": 2000,
                            "segment_end_ms": 4000,
                        },
                    ]
                }
            }
        }
    )

    assert result["status"] == "ready"
    assert result["artifact_id"] == "learner-contact-sheet-artifact"
    assert len(result["assets"]) == 2
    assert {asset["source_kind"] for asset in result["assets"]} == {"learner_capture"}
    assert {asset["capture_session_id"] for asset in result["assets"]} == {
        "device_session_capture_1"
    }
    assert all(asset["motion_window_ref"] for asset in result["assets"])
    assert [asset["capture_ms"] for asset in result["assets"]] == [1000.0, 3000.0]
    assert [asset["motion_window_ref"] for asset in result["assets"]] == [
        "lms-live-capture:rtmp-window:0:0",
        "lms-live-capture:rtmp-window:2000:1",
    ]
    assert requests[0]["metadata"]["capture_input_uri"].startswith("rtmp://")
    assert requests[0]["metadata"]["adaptive_segment_frame_count"] == 2
    assert recorder.window_dir.exists()

    recorder.cleanup_transient_frames()

    assert not recorder.window_dir.exists()


def test_api_post_rejection_surfaces_bounded_response_detail(monkeypatch) -> None:
    class Response:
        status_code = 422
        text = ""

        @staticmethod
        def json() -> dict[str, str]:
            return {"detail": "learner visual evidence requires motion_window_ref"}

        @staticmethod
        def raise_for_status() -> None:
            import requests

            raise requests.HTTPError("422 Client Error")

    monkeypatch.setattr(api_client.requests, "post", lambda *_args, **_kwargs: Response())

    try:
        api_client.api_post("http://localhost:8200", "/practice-diaries", {})
    except RuntimeError as exc:
        assert str(exc) == (
            "api_post_rejected:422:/practice-diaries:"
            "learner visual evidence requires motion_window_ref"
        )
    else:
        raise AssertionError("api_post must reject a 422 response")


def test_transient_cleanup_failure_does_not_invalidate_durable_closeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[dict] = []
    recorder = evidence.LearnerVisualEvidenceRecorder(
        _args(tmp_path, "rtmp://example.test/live"),
        "lms-cleanup-failure",
    )
    monkeypatch.setattr(evidence, "emit", events.append)
    monkeypatch.setattr(
        evidence.shutil,
        "rmtree",
        lambda _path: (_ for _ in ()).throw(OSError("filesystem busy")),
    )

    recorder.cleanup_transient_frames()

    assert recorder.window_dir.exists()
    assert events == [
        {
            "event": "learner_visual_evidence_transient_cleanup_failed",
            "captured_window_frame_count": 0,
            "error": "filesystem busy",
        }
    ]
