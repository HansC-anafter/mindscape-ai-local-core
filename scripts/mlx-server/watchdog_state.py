#!/usr/bin/env python3
"""Read local VLM inflight state for the host-side MLX watchdog."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Optional


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--hard-timeout", type=float, default=1800.0)
    parser.add_argument("--heartbeat-timeout", type=float, default=120.0)
    args = parser.parse_args()

    state_path = Path(args.state_file)
    if not state_path.exists():
        print("missing")
        return 1

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"unreadable: {exc}")
        return 1

    if payload.get("status") != "active":
        print(f"inactive status={payload.get('status')!r}")
        return 1

    started_at = _coerce_float(payload.get("started_at"))
    heartbeat_at = _coerce_float(payload.get("heartbeat_at")) or started_at
    if started_at is None or heartbeat_at is None:
        print("stale missing_timestamp")
        return 1

    now = time.time()
    age = max(0.0, now - started_at)
    heartbeat_age = max(0.0, now - heartbeat_at)
    if age > args.hard_timeout:
        print(f"stale hard_timeout age={age:.1f}s")
        return 1
    if heartbeat_age > args.heartbeat_timeout:
        print(f"stale heartbeat_timeout heartbeat_age={heartbeat_age:.1f}s")
        return 1

    phase = payload.get("phase") or "unknown"
    reference_id = payload.get("reference_id") or "unknown"
    print(f"active phase={phase} ref={reference_id} age={age:.1f}s heartbeat_age={heartbeat_age:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
