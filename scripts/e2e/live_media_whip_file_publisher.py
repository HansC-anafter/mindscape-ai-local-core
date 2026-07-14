#!/usr/bin/env python3
"""Publish a bounded local video asset through a live session's WHIP endpoint."""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from scripts.e2e.live_media_device_source_client import _write_private_json
except ModuleNotFoundError:
    from live_media_device_source_client import _write_private_json


def _load_private_access(path: Path, *, minimum_lifetime_sec: float) -> dict[str, Any]:
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("live_media_access_permissions_invalid")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("live_media_access_invalid")
    session = payload.get("session")
    tokens = payload.get("tokens")
    if not isinstance(session, dict) or not isinstance(tokens, dict):
        raise ValueError("live_media_access_invalid")
    endpoint = str((session.get("endpoints") or {}).get("whip_publish_url") or "")
    token = str(tokens.get("publish") or "")
    if not endpoint.startswith("https://") or not token:
        raise ValueError("live_media_whip_access_missing")
    if float(session.get("expires_at_epoch") or 0) <= time.time() + minimum_lifetime_sec:
        raise ValueError("live_media_access_expires_too_soon")
    return payload


def _ffmpeg_args(
    *,
    ffmpeg_bin: Path,
    source_path: Path,
    access: dict[str, Any],
    duration_sec: float,
) -> list[str]:
    session = access["session"]
    args = [
        str(ffmpeg_bin),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stream_loop",
        "-1",
        "-re",
        "-i",
        str(source_path),
        "-an",
        "-vf",
        (
            "scale=960:540:force_original_aspect_ratio=decrease,"
            "pad=960:540:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-profile:v",
        "baseline",
        "-level",
        "3.1",
        "-b:v",
        "1800k",
        "-maxrate",
        "2200k",
        "-bufsize",
        "3600k",
        "-g",
        "60",
        "-keyint_min",
        "60",
        "-sc_threshold",
        "0",
    ]
    if duration_sec > 0:
        args.extend(["-t", str(duration_sec)])
    args.extend(
        [
            "-f",
            "whip",
            "-authorization",
            access["tokens"]["publish"],
            "-handshake_timeout",
            "15000",
            session["endpoints"]["whip_publish_url"],
        ]
    )
    return args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--access-path", type=Path, required=True)
    parser.add_argument("--source-path", type=Path, required=True)
    parser.add_argument("--state-path", type=Path, required=True)
    parser.add_argument(
        "--ffmpeg-bin",
        type=Path,
        default=Path("/opt/homebrew/bin/ffmpeg"),
    )
    parser.add_argument("--duration-sec", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source_path.is_file():
        raise SystemExit("live_media_source_file_not_found")
    if not args.ffmpeg_bin.is_file():
        raise SystemExit("live_media_ffmpeg_not_found")
    minimum_lifetime_sec = max(60.0, args.duration_sec + 60.0)
    access = _load_private_access(
        args.access_path,
        minimum_lifetime_sec=minimum_lifetime_sec,
    )
    session = access["session"]
    state = {
        "schema_version": "live_media_whip_file_publisher_e2e.v1",
        "status": "starting",
        "workspace_id": session.get("workspace_id"),
        "device_session_id": session.get("device_session_id"),
        "media_session_id": session.get("media_session_id"),
        "source_path": str(args.source_path),
        "duration_sec": max(0.0, args.duration_sec),
        "started_at_epoch": time.time(),
    }
    child = subprocess.Popen(
        _ffmpeg_args(
            ffmpeg_bin=args.ffmpeg_bin,
            source_path=args.source_path,
            access=access,
            duration_sec=args.duration_sec,
        ),
        stdin=subprocess.DEVNULL,
    )
    state.update({"status": "publishing", "pid": child.pid})
    _write_private_json(args.state_path, state)

    def stop_child(_signum: int, _frame: Any) -> None:
        if child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGINT, stop_child)
    signal.signal(signal.SIGTERM, stop_child)
    return_code = child.wait()
    state["status"] = "completed" if return_code == 0 else "failed"
    state["return_code"] = return_code
    state["ended_at_epoch"] = time.time()
    _write_private_json(args.state_path, state)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
