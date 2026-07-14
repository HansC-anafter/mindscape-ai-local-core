from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path

import pytest


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

from rtmp_motion_publisher.live_receiver_runtime import (  # noqa: E402
    _build_receiver_args,
    _load_descriptor,
)
from rtmp_motion_publisher import api_client  # noqa: E402
from rtmp_motion_publisher.receiver_state import (  # noqa: E402
    close_receiver_state_reporter,
    transition_receiver_state,
)


def _descriptor() -> dict:
    return {
        "schema_version": "live_media_receiver.v1",
        "workspace_id": "workspace-one",
        "device_session_id": "device-one",
        "media_session_id": "media-one",
        "live_motion_session_id": "motion-one",
        "meeting_session_id": "meeting-one",
        "practice_session_id": "practice-one",
        "receiver_identity": "receiver-one",
        "append_owner_id": "append-one",
        "source_kind": "phone_camera",
        "transport_kind": "rtsps",
        "input_url": "rtsps://media.example.test:8322/live/path",
        "access_token": "secret-token",
        "expires_at_epoch": time.time() + 3600,
        "api_base": "http://127.0.0.1:8200",
        "coach_pack": "yogacoach",
        "practice_mode": "live_guidance",
        "reference_url": "https://example.test/reference",
        "user_goal": "steady alignment",
        "expected_duration_ms": 0,
    }


def _write_descriptor(tmp_path: Path, mode: int = 0o600) -> Path:
    path = tmp_path / "receiver.json"
    path.write_text(json.dumps(_descriptor()), encoding="utf-8")
    path.chmod(mode)
    return path


def test_descriptor_builds_formal_rtsps_receiver_args(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_HOST_DIR", str(tmp_path / "runtime-data"))
    descriptor = _load_descriptor(_write_descriptor(tmp_path))

    args = _build_receiver_args(descriptor, state_path=tmp_path / "state.json")

    assert args.transport_kind == "rtsps"
    assert args.source_kind == "phone_camera"
    assert args.capture_backend == "ffmpeg"
    assert args.api_timeout_sec == 5.0
    assert args.control_api_timeout_sec == 30.0
    assert args.rollup_api_timeout_sec == 30.0
    assert args.rollup_every_sec == 0.0
    assert args.closeout_api_timeout_sec == 30.0
    assert args.api_retry_count == 2
    assert args.append_queue_max_size == 32
    assert args.rtmp_url.startswith("rtsps://media.example.test:8322/live/path?")
    assert "token=secret-token" in args.rtmp_url
    assert args.append_owner_id == "append-one"
    assert args.receiver_identity == "receiver-one"
    assert args.media_session_id == "media-one"
    assert args.emit_yogacoach_summary is True
    assert args.materialize_practice_diary is True
    assert str(tmp_path / "runtime-data") in args.learner_evidence_output_dir


def test_descriptor_passes_only_device_node_resolved_reference_profile_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "runtime-data"
    profile_path = (
        data_root
        / "workspaces/workspace-one/artifacts/yogacoach/reference-profiles/reference.json"
    )
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_CORE_DATA_HOST_DIR", str(data_root))
    descriptor = _descriptor()
    descriptor["motion_reference_profile"] = {
        "artifact_id": "artifact-one",
        "storage_ref": (
            "/app/data/workspaces/workspace-one/artifacts/yogacoach/"
            "reference-profiles/reference.json"
        ),
        "reference_profile_id": "reference-one",
    }
    descriptor["motion_reference_profile_path"] = str(profile_path)
    path = tmp_path / "receiver-with-profile.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    path.chmod(0o600)

    args = _build_receiver_args(
        _load_descriptor(path),
        state_path=tmp_path / "state.json",
    )

    assert args.motion_reference_profile_path == str(profile_path.resolve())


def test_descriptor_rejects_group_readable_credentials(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="receiver_descriptor_permissions_invalid"):
        _load_descriptor(_write_descriptor(tmp_path, mode=0o640))


def test_descriptor_rejects_non_rtsps_input(tmp_path: Path) -> None:
    descriptor = _descriptor()
    descriptor["input_url"] = "rtmp://media.example.test/live/path"
    path = tmp_path / "receiver.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ValueError, match="receiver_input_must_use_rtsps"):
        _load_descriptor(path)


def test_formal_receiver_registration_restores_append_ownership_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_HOST_DIR", str(tmp_path / "runtime-data"))
    args = _build_receiver_args(
        _load_descriptor(_write_descriptor(tmp_path)),
        state_path=tmp_path / "state.json",
    )
    payloads: list[dict] = []
    call_options: list[dict] = []
    monkeypatch.setattr(
        api_client,
        "api_post",
        lambda _base, _path, payload, **kwargs: payloads.append(payload)
        or call_options.append(kwargs)
        or {"live_session": {"live_session_id": "motion-one"}},
    )
    monkeypatch.setattr(api_client, "emit", lambda _event: None)

    assert api_client.register_live_session(args) == "motion-one"
    metadata = payloads[0]["metadata"]
    assert metadata["append_owner_required"] is True
    assert metadata["capture_input_kind"] == "remote_webrtc"
    assert metadata["source_kind"] == "phone_camera"
    assert "append_owner_id" not in metadata
    assert call_options[0]["timeout_sec"] == 30.0


def test_receiver_state_emits_bounded_authenticated_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCAL_CORE_DATA_HOST_DIR", str(tmp_path / "runtime-data"))
    args = _build_receiver_args(
        _load_descriptor(_write_descriptor(tmp_path)),
        state_path=tmp_path / "state.json",
    )
    calls: list[dict] = []

    class Response:
        status_code = 200

    monkeypatch.setattr(
        "rtmp_motion_publisher.receiver_state.requests.post",
        lambda url, **kwargs: calls.append({"url": url, **kwargs}) or Response(),
    )

    transition_receiver_state(
        args,
        "analyzing",
        metrics={
            "attempted_windows": 7,
            "accepted_windows": 7,
            "decoded_frames": 35,
            "overwritten_frames": 4,
            "decode_errors": 1,
            "pipe_bytes_read": 240000,
            "pipe_buffered_bytes": 128,
            "pipe_high_watermark_bytes": 28000,
            "pipe_discarded_bytes": 12,
            "pipe_overflow_count": 0,
            "reference_chapter_id": "segment:010",
            "reference_localization_ready": True,
            "raw_frames": ["forbidden"],
        },
    )
    close_receiver_state_reporter()

    assert len(calls) == 1
    assert calls[0]["url"].endswith(
        "/media-sessions/media-one/receiver/events"
    )
    assert calls[0]["headers"]["Authorization"] == "Bearer append-one"
    assert calls[0]["json"]["metrics"] == {
        "attempted_windows": 7,
        "accepted_windows": 7,
        "rejected_windows": 0,
        "failed_windows": 0,
        "append_queue_pending": 0,
        "reconnect_attempts": 0,
        "decoded_frames": 35,
        "overwritten_frames": 4,
        "decode_errors": 1,
        "pipe_bytes_read": 240000,
        "pipe_buffered_bytes": 128,
        "pipe_high_watermark_bytes": 28000,
        "pipe_discarded_bytes": 12,
        "pipe_overflow_count": 0,
        "reference_chapter_id": "segment:010",
        "reference_localization_ready": True,
    }
    assert "append-one" not in json.dumps(calls[0]["json"])
