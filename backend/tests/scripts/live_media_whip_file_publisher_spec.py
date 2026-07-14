from __future__ import annotations

import json
import os

import pytest

from scripts.e2e.live_media_whip_file_publisher import (
    _ffmpeg_args,
    _load_private_access,
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


def test_ffmpeg_command_uses_whip_and_bounded_duration(tmp_path) -> None:
    args = _ffmpeg_args(
        ffmpeg_bin=tmp_path / "ffmpeg",
        source_path=tmp_path / "lesson.mp4",
        access=_access(),
        duration_sec=210.0,
    )

    assert args[args.index("-f") + 1] == "whip"
    assert args[args.index("-t") + 1] == "210.0"
    assert args[args.index("-authorization") + 1] == "publish-secret"
    assert args[-1] == "https://media.test/live/path/whip"
