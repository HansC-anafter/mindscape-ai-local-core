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


E2E_CAMERA_FPS = 30
E2E_H264_PROFILE = "baseline"
E2E_H264_MAX_B_FRAMES = 0
FORMAL_RECEIVER_STARTUP_GRACE_SEC = 120.0
FORMAL_RECEIVER_SHUTDOWN_GRACE_SEC = 30.0
FORMAL_SOURCE_RECONNECT_DELAYS_SEC = (1.5, 5.0, 15.0)
FORMAL_SOURCE_STABLE_RESET_SEC = 30.0


def _publisher_duration_sec(analysis_duration_sec: float) -> float:
    if analysis_duration_sec <= 0:
        raise ValueError("analysis_duration_must_be_positive")
    return (
        analysis_duration_sec
        + FORMAL_RECEIVER_STARTUP_GRACE_SEC
        + FORMAL_RECEIVER_SHUTDOWN_GRACE_SEC
    )


def _next_reconnect_delay_sec(
    *,
    consecutive_failures: int,
    published_sec: float,
) -> tuple[float | None, int]:
    if published_sec >= FORMAL_SOURCE_STABLE_RESET_SEC:
        consecutive_failures = 0
    if consecutive_failures >= len(FORMAL_SOURCE_RECONNECT_DELAYS_SEC):
        return None, consecutive_failures
    return (
        FORMAL_SOURCE_RECONNECT_DELAYS_SEC[consecutive_failures],
        consecutive_failures + 1,
    )


def _publisher_terminal_status(*, return_code: int, stop_requested: bool) -> str:
    if stop_requested:
        return "stopped"
    return "completed" if return_code == 0 else "failed"


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
    publisher_duration_sec: float,
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
            "pad=960:540:(ow-iw)/2:(oh-ih)/2,"
            f"fps={E2E_CAMERA_FPS},setpts=N/({E2E_CAMERA_FPS}*TB),"
            "format=yuv420p"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-profile:v",
        E2E_H264_PROFILE,
        "-bf",
        str(E2E_H264_MAX_B_FRAMES),
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
    args.extend(["-t", str(publisher_duration_sec)])
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
    parser.add_argument("--analysis-duration-sec", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source_path.is_file():
        raise SystemExit("live_media_source_file_not_found")
    if not args.ffmpeg_bin.is_file():
        raise SystemExit("live_media_ffmpeg_not_found")
    try:
        publisher_duration_sec = _publisher_duration_sec(args.analysis_duration_sec)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    minimum_lifetime_sec = publisher_duration_sec + 60.0
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
        "analysis_duration_sec": args.analysis_duration_sec,
        "publisher_duration_sec": publisher_duration_sec,
        "video_codec": "h264",
        "h264_profile": E2E_H264_PROFILE,
        "max_b_frames": E2E_H264_MAX_B_FRAMES,
        "receiver_startup_grace_sec": FORMAL_RECEIVER_STARTUP_GRACE_SEC,
        "receiver_shutdown_grace_sec": FORMAL_RECEIVER_SHUTDOWN_GRACE_SEC,
        "started_at_epoch": time.time(),
    }
    child: subprocess.Popen[bytes] | None = None
    stop_requested = False

    def stop_child(_signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True
        if child is not None and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGINT, stop_child)
    signal.signal(signal.SIGTERM, stop_child)
    deadline = time.monotonic() + publisher_duration_sec
    return_code = 1
    reconnect_count = 0
    consecutive_failures = 0
    publish_attempt_count = 0
    while True:
        remaining_sec = deadline - time.monotonic()
        if remaining_sec <= 0:
            return_code = 0
            break
        publish_attempt_count += 1
        attempt_started = time.monotonic()
        child = subprocess.Popen(
            _ffmpeg_args(
                ffmpeg_bin=args.ffmpeg_bin,
                source_path=args.source_path,
                access=access,
                publisher_duration_sec=remaining_sec,
            ),
            stdin=subprocess.DEVNULL,
        )
        state.update(
            {
                "status": "publishing",
                "pid": child.pid,
                "publish_attempt_count": publish_attempt_count,
                "reconnect_count": reconnect_count,
            }
        )
        _write_private_json(args.state_path, state)
        return_code = child.wait()
        published_sec = max(0.0, time.monotonic() - attempt_started)
        if return_code == 0 or stop_requested:
            break
        delay_sec, consecutive_failures = _next_reconnect_delay_sec(
            consecutive_failures=consecutive_failures,
            published_sec=published_sec,
        )
        if delay_sec is None or time.monotonic() + delay_sec >= deadline:
            break
        reconnect_count += 1
        state.update(
            {
                "status": "reconnecting",
                "last_return_code": return_code,
                "last_publish_uptime_sec": published_sec,
                "next_reconnect_delay_sec": delay_sec,
                "reconnect_count": reconnect_count,
            }
        )
        _write_private_json(args.state_path, state)
        time.sleep(delay_sec)
    state["status"] = _publisher_terminal_status(
        return_code=return_code,
        stop_requested=stop_requested,
    )
    state["return_code"] = return_code
    state["reconnect_count"] = reconnect_count
    state["publish_attempt_count"] = publish_attempt_count
    state["ended_at_epoch"] = time.time()
    _write_private_json(args.state_path, state)
    return 0 if stop_requested else return_code


if __name__ == "__main__":
    raise SystemExit(main())
