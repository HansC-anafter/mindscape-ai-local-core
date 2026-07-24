from __future__ import annotations

import json
import os

import pytest

from scripts.e2e.live_media_whip_file_publisher import (
    E2E_H264_MAX_B_FRAMES,
    E2E_H264_PROFILE,
    FORMAL_RECEIVER_STARTUP_GRACE_SEC,
    FORMAL_RECEIVER_SHUTDOWN_GRACE_SEC,
    FORMAL_SOURCE_RECONNECT_DELAYS_SEC,
    _ffmpeg_args,
    _load_private_access,
    _next_reconnect_delay_sec,
    _publisher_duration_sec,
    _publisher_terminal_status,
)


def _access() -> dict:
    return {
        "session": {
            "workspace_id": "workspace-one",
            "device_session_id": "device-one",
            "media_session_id": "media-one",
            "expires_at_epoch": 4102444800,
            "endpoints": {"whip_publish_url": "https://media.test/live/path/whip"},
        },
        "tokens": {"publish": "publish-secret", "preview": "preview-secret"},
    }


def test_load_access_requires_owner_only_file_and_minimum_lifetime(tmp_path) -> None:
    path = tmp_path / "access.json"
    path.write_text(json.dumps(_access()), encoding="utf-8")
    path.chmod(0o600)

    loaded = _load_private_access(path, minimum_lifetime_sec=1800)

    assert loaded["session"]["media_session_id"] == "media-one"


def test_load_access_rejects_group_readable_file(tmp_path) -> None:
    path = tmp_path / "access.json"
    path.write_text(json.dumps(_access()), encoding="utf-8")
    os.chmod(path, 0o640)

    with pytest.raises(ValueError, match="live_media_access_permissions_invalid"):
        _load_private_access(path, minimum_lifetime_sec=60)


def test_publisher_outlives_analysis_by_startup_and_shutdown_grace() -> None:
    assert _publisher_duration_sec(1800.0) == (
        1800.0
        + FORMAL_RECEIVER_STARTUP_GRACE_SEC
        + FORMAL_RECEIVER_SHUTDOWN_GRACE_SEC
    )


def test_publisher_duration_requires_positive_analysis_duration() -> None:
    with pytest.raises(ValueError, match="analysis_duration_must_be_positive"):
        _publisher_duration_sec(0.0)


def test_reconnect_policy_matches_bounded_phone_media_backoff() -> None:
    consecutive = 0
    observed = []
    for _ in FORMAL_SOURCE_RECONNECT_DELAYS_SEC:
        delay, consecutive = _next_reconnect_delay_sec(
            consecutive_failures=consecutive,
            published_sec=0.0,
        )
        observed.append(delay)

    assert tuple(observed) == FORMAL_SOURCE_RECONNECT_DELAYS_SEC
    assert _next_reconnect_delay_sec(
        consecutive_failures=consecutive,
        published_sec=0.0,
    )[0] is None


def test_stable_publish_resets_consecutive_reconnect_budget() -> None:
    delay, consecutive = _next_reconnect_delay_sec(
        consecutive_failures=len(FORMAL_SOURCE_RECONNECT_DELAYS_SEC),
        published_sec=30.0,
    )

    assert delay == FORMAL_SOURCE_RECONNECT_DELAYS_SEC[0]
    assert consecutive == 1


def test_requested_stop_is_not_reported_as_publisher_failure() -> None:
    assert _publisher_terminal_status(
        return_code=255,
        stop_requested=True,
    ) == "stopped"
    assert _publisher_terminal_status(
        return_code=255,
        stop_requested=False,
    ) == "failed"


def test_ffmpeg_command_uses_whip_and_bounded_duration(tmp_path) -> None:
    args = _ffmpeg_args(
        ffmpeg_bin=tmp_path / "ffmpeg",
        source_path=tmp_path / "lesson.mp4",
        access=_access(),
        publisher_duration_sec=210.0,
    )

    assert args[args.index("-f") + 1] == "whip"
    assert args[args.index("-t") + 1] == "210.0"
    assert args[args.index("-authorization") + 1] == "publish-secret"
    assert "fps=30,setpts=N/(30*TB)" in args[args.index("-vf") + 1]
    assert args[args.index("-profile:v") + 1] == E2E_H264_PROFILE
    assert args[args.index("-bf") + 1] == str(E2E_H264_MAX_B_FRAMES)
    assert args[-1] == "https://media.test/live/path/whip"
