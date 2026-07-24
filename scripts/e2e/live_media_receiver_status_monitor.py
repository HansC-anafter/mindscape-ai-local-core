#!/usr/bin/env python3
"""Record bounded Local Core live-media receiver status until terminal."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = frozenset({"completed", "failed", "expired", "not_found"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-session-id", required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--mcp-url", default="http://127.0.0.1:3100/mcp")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    parser.add_argument("--timeout-seconds", type=float, default=2_200.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=10.0)
    return parser.parse_args()


def build_request(media_session_id: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": f"receiver-monitor:{media_session_id}",
        "method": "tools/call",
        "params": {
            "name": "capture_relay_control",
            "arguments": {
                "action": "receiver_status",
                "media_session_id": media_session_id,
            },
        },
    }


def read_receiver_status(
    *,
    mcp_url: str,
    request_payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        mcp_url,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        envelope = json.load(response)
    content = ((envelope.get("result") or {}).get("content") or [])
    if not content or not isinstance(content[0], dict):
        raise ValueError("receiver_status_content_missing")
    payload = json.loads(str(content[0].get("text") or ""))
    if not isinstance(payload, dict):
        raise ValueError("receiver_status_payload_invalid")
    return payload


def compact_status(sample: dict[str, Any]) -> dict[str, Any]:
    metrics = sample.get("metrics") if isinstance(sample.get("metrics"), dict) else {}
    return {
        "observed_at": sample.get("observed_at"),
        "status": sample.get("status"),
        "state": sample.get("state"),
        "accepted": metrics.get("accepted_windows"),
        "rejected": metrics.get("rejected_windows"),
        "failed": metrics.get("failed_windows"),
        "pending": metrics.get("append_queue_pending"),
        "reconnect": metrics.get("reconnect_attempts"),
        "decode_errors": metrics.get("decode_errors"),
        "overflow": metrics.get("pipe_overflow_count"),
        "last_window_end_ms": metrics.get("last_window_end_ms"),
    }


def main() -> int:
    args = parse_args()
    if args.interval_seconds <= 0 or args.timeout_seconds <= 0:
        raise SystemExit("receiver_monitor_duration_invalid")
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    request_payload = build_request(args.media_session_id)
    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        try:
            status = read_receiver_status(
                mcp_url=args.mcp_url,
                request_payload=request_payload,
                timeout_seconds=args.request_timeout_seconds,
            )
            sample = {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                **status,
            }
        except Exception as exc:
            sample = {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "status": "monitor_error",
                "reason": f"{type(exc).__name__}:{exc}",
            }
        with args.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, ensure_ascii=True, sort_keys=True) + "\n")
        print(json.dumps(compact_status(sample), sort_keys=True), flush=True)
        if sample.get("status") in TERMINAL_STATUSES:
            return 0
        time.sleep(args.interval_seconds)
    raise SystemExit("receiver_monitor_timeout")


if __name__ == "__main__":
    raise SystemExit(main())
