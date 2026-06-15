#!/usr/bin/env python3
"""Read local VLM inflight state for the host-side MLX watchdog."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_timestamp(value: Any) -> Optional[float]:
    numeric = _coerce_float(value)
    if numeric is not None:
        return numeric
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("legacy_state_file", nargs="?")
    parser.add_argument("--state-file")
    parser.add_argument("--hard-timeout", type=float, default=7200.0)
    parser.add_argument("--heartbeat-timeout", type=float, default=None)
    parser.add_argument("--heartbeat-ttl", type=float, default=None)
    parser.add_argument("--now", type=float, default=None)
    args = parser.parse_args()

    state_file = args.state_file or args.legacy_state_file
    if not state_file:
        parser.error("--state-file is required")
    legacy_mode = args.state_file is None
    heartbeat_timeout = (
        args.heartbeat_timeout
        if args.heartbeat_timeout is not None
        else args.heartbeat_ttl
        if args.heartbeat_ttl is not None
        else 120.0
    )
    min_hard_timeout = _coerce_float(
        os.getenv("MLX_WATCHDOG_MIN_HARD_TIMEOUT_SECONDS")
    )
    hard_timeout = args.hard_timeout
    if not legacy_mode:
        hard_timeout = max(hard_timeout, min_hard_timeout or 7200.0)

    state_path = Path(state_file)
    if not state_path.exists():
        if not legacy_mode:
            print("missing")
        return 1

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if not legacy_mode:
            print(f"unreadable: {exc}")
        return 1

    if payload.get("status") != "active":
        if not legacy_mode:
            print(f"inactive status={payload.get('status')!r}")
        return 1

    started_at = _coerce_timestamp(payload.get("started_at"))
    if started_at is None:
        started_at = _coerce_float(payload.get("started_at_epoch"))
    heartbeat_at = _coerce_timestamp(payload.get("heartbeat_at"))
    if heartbeat_at is None:
        heartbeat_at = _coerce_float(payload.get("heartbeat_at_epoch"))
    if heartbeat_at is None:
        heartbeat_at = started_at
    if started_at is None or heartbeat_at is None:
        if not legacy_mode:
            print("stale missing_timestamp")
        return 1

    now = args.now if args.now is not None else time.time()
    age = max(0.0, now - started_at)
    heartbeat_age = max(0.0, now - heartbeat_at)
    request_id = payload.get("request_id") or payload.get("reference_id") or "unknown"

    if legacy_mode:
        if age > args.hard_timeout:
            print(f"hard_timeout\t{request_id}\t{age:.0f}\t{heartbeat_age:.0f}")
            return 0
        if heartbeat_age > heartbeat_timeout:
            print(f"stale\t{request_id}\t{age:.0f}\t{heartbeat_age:.0f}")
            return 0
        print(f"heartbeat_fresh\t{request_id}\t{age:.0f}\t{heartbeat_age:.0f}")
        return 0

    phase = payload.get("phase") or "unknown"
    reference_id = payload.get("reference_id") or "unknown"
    grace_until = _coerce_float(payload.get("grace_until"))
    if phase == "client_timeout_grace" and grace_until is not None and now < grace_until:
        grace_remaining = max(0.0, grace_until - now)
        print(
            "active "
            f"phase={phase} ref={reference_id} age={age:.1f}s "
            f"heartbeat_age={heartbeat_age:.1f}s grace_remaining={grace_remaining:.1f}s"
        )
        return 0

    if age > hard_timeout:
        print(f"stale hard_timeout age={age:.1f}s")
        return 1
    if heartbeat_age > heartbeat_timeout:
        print(f"stale heartbeat_timeout heartbeat_age={heartbeat_age:.1f}s")
        return 1

    print(f"active phase={phase} ref={reference_id} age={age:.1f}s heartbeat_age={heartbeat_age:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
