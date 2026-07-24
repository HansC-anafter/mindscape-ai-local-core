from argparse import Namespace
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from rtmp_motion_publisher.retained_video import (  # noqa: E402
    RetainedVideoProbe,
    probe_retained_video,
    read_mp4_movie_header_duration_ms,
    register_retained_video,
    sha256_file,
    validate_retained_video_coverage,
)


def _mp4_box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, box_type) + payload


def _write_mp4_movie_header(path: Path, *, duration: int) -> None:
    movie_header = b"\x00\x00\x00\x00" + struct.pack(">IIII", 0, 0, 1000, duration)
    path.write_bytes(
        _mp4_box(b"ftyp", b"isom")
        + _mp4_box(b"moov", _mp4_box(b"mvhd", movie_header))
    )


def _args() -> Namespace:
    return Namespace(
        api_base="http://localhost:8200",
        workspace_id="workspace-1",
        meeting_id="meeting-1",
        source_session_id="device-session-1",
        media_session_id="media-session-1",
        receiver_identity="receiver-1",
        transport_kind="rtsps",
        api_timeout_sec=1.0,
        api_retry_count=1,
        api_retry_backoff_sec=0.0,
    )


def test_retained_video_requires_one_contiguous_capture_part(tmp_path: Path) -> None:
    (tmp_path / "learner-capture-part-000.mp4").write_bytes(b"part-0")
    (tmp_path / "learner-capture-part-001.mp4").write_bytes(b"part-1")

    try:
        register_retained_video(
            args=_args(),
            host_root=tmp_path,
            storage_root=Path("/app/evidence"),
            live_session_id="live-1",
            segments=[{"segment_end_ms": 2000}],
            input_kind="remote_webrtc",
            input_uri="rtsps://media.test/live",
            probe=lambda _path: RetainedVideoProbe(
                2000,
                2000,
                "h264",
                1920,
                1080,
            ),
            register_artifact=lambda *_args, **_kwargs: {"id": "artifact-1"},
        )
    except RuntimeError as exc:
        assert str(exc) == "learner_retained_video_requires_single_contiguous_part:2"
    else:
        raise AssertionError("multiple retained parts must fail closed")


def test_retained_video_coverage_fails_closed_when_duration_is_short() -> None:
    probe = RetainedVideoProbe(1000.0, 1000.0, "h264", 1920, 1080)

    try:
        validate_retained_video_coverage(
            probe,
            [{"segment_start_ms": 0, "segment_end_ms": 2000}],
        )
    except RuntimeError as exc:
        assert str(exc) == "learner_retained_video_coverage_short:1000.0:2000.0"
    else:
        raise AssertionError("short retained video must fail closed")


def test_retained_video_coverage_uses_browser_seekable_duration() -> None:
    probe = RetainedVideoProbe(2000.0, 1000.0, "h264", 1920, 1080)

    try:
        validate_retained_video_coverage(
            probe,
            [{"segment_start_ms": 0, "segment_end_ms": 1600}],
        )
    except RuntimeError as exc:
        assert str(exc) == "learner_retained_video_coverage_short:1000.0:1600.0"
    else:
        raise AssertionError("browser-short retained video must fail closed")


def test_retained_video_registration_persists_browser_metadata_duration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learner-capture-part-000.mp4"
    path.write_bytes(b"retained-video")
    requests: list[dict] = []

    result = register_retained_video(
        args=_args(),
        host_root=tmp_path,
        storage_root=Path("/app/evidence"),
        live_session_id="live-1",
        segments=[{"segment_end_ms": 1900}],
        input_kind="remote_webrtc",
        input_uri="rtsps://media.test/live",
        probe=lambda _path: RetainedVideoProbe(
            2000,
            1900,
            "h264",
            1920,
            1080,
        ),
        register_artifact=lambda _base, _route, payload, **_kwargs: (
            requests.append(payload) or {"id": "artifact-1"}
        ),
    )

    assert result.artifact_id == "artifact-1"
    assert result.duration_ms == 1900
    assert requests[0]["metadata"]["media_duration_ms"] == 2000
    assert requests[0]["metadata"]["browser_metadata_duration_ms"] == 1900
    assert requests[0]["metadata"]["playback_duration_ms"] == 1900
    assert requests[0]["metadata"]["lineage"] == (
        "learner_capture_retained_by_analysis_reader"
    )


def test_retained_video_checksum_is_streamed_without_read_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "retained.mp4"
    payload = b"bounded-video-payload" * 32
    path.write_bytes(payload)

    def reject_read_bytes(_path: Path) -> bytes:
        raise AssertionError("retained video checksum must not buffer the whole file")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)

    assert sha256_file(path, chunk_bytes=17) == hashlib.sha256(payload).hexdigest()


def test_retained_video_probe_requires_readable_video_stream(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "retained.mp4"
    _write_mp4_movie_header(path, duration=4971)
    payload = {
        "format": {"duration": "4.971"},
        "streams": [
            {
                "codec_name": "h264",
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
            }
        ],
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    assert probe_retained_video(
        path,
        ffmpeg_bin="/opt/homebrew/bin/ffmpeg",
        timeout_sec=5.0,
    ) == RetainedVideoProbe(4971.0, 4971.0, "h264", 1920, 1080)


def test_retained_video_rejects_zero_duration_mp4_movie_header(
    tmp_path: Path,
) -> None:
    path = tmp_path / "fragmented.mp4"
    _write_mp4_movie_header(path, duration=0)

    try:
        read_mp4_movie_header_duration_ms(path)
    except RuntimeError as exc:
        assert str(exc) == "learner_retained_video_browser_metadata_invalid"
    else:
        raise AssertionError("zero-duration MP4 metadata must fail closed")


def test_retained_video_rejects_unknown_mp4_movie_header_duration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unknown-duration.mp4"
    _write_mp4_movie_header(path, duration=0xFFFFFFFF)

    try:
        read_mp4_movie_header_duration_ms(path)
    except RuntimeError as exc:
        assert str(exc) == "learner_retained_video_browser_metadata_invalid"
    else:
        raise AssertionError("unknown MP4 duration must fail closed")


def test_retained_video_rejects_decoder_browser_duration_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "duration-mismatch.mp4"
    _write_mp4_movie_header(path, duration=4971)
    payload = {
        "format": {"duration": "8.000"},
        "streams": [{
            "codec_name": "h264",
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
        }],
    }
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )

    try:
        probe_retained_video(
            path,
            ffmpeg_bin="/opt/homebrew/bin/ffmpeg",
            timeout_sec=5.0,
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "learner_retained_video_browser_duration_mismatch:8000.0:4971.0"
        )
    else:
        raise AssertionError("decoder/browser duration mismatch must fail closed")
