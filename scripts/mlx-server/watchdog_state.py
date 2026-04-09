#!/usr/bin/env python3
"""Evaluate MLX inflight watchdog state."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read MLX watchdog inflight state")
    parser.add_argument("state_file", type=Path)
    parser.add_argument("--heartbeat-ttl", type=int, required=True)
    parser.add_argument("--hard-timeout", type=int, required=True)
    parser.add_argument("--prefill-timeout", type=int, required=True)
    parser.add_argument("--active-phase-timeout", type=int, required=True)
    parser.add_argument("--now", type=float, default=None)
    return parser


def _safe_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def main() -> int:
    args = _build_parser().parse_args()
    try:
        data = json.loads(args.state_file.read_text(encoding="utf-8"))
    except Exception:
        return 1

    if str(data.get("status") or "") != "active":
        return 1

    now = args.now if args.now is not None else time.time()
    request_id = str(data.get("request_id") or "")
    phase = str(data.get("progress_phase") or "")
    started = _safe_float(data.get("started_at_epoch"))
    heartbeat = _safe_float(data.get("heartbeat_at_epoch"))
    progress = _safe_float(data.get("progress_at_epoch"))
    phase_entered = _safe_float(data.get("phase_entered_at_epoch"))
    request_age = max(0, int(now - started)) if started else 0
    heartbeat_age = max(0, int(now - heartbeat)) if heartbeat else 10**9
    progress_age = max(0, int(now - progress)) if progress else 10**9
    phase_age = max(0, int(now - phase_entered)) if phase_entered else request_age

    prefill_phases = {"accepted", "embedding", "prefill", "model_loading"}
    active_inference_phases = {"model_ready", "decode_ready", "generating"}
    # Local MLX requests can legitimately sit in model_ready / generating for
    # many minutes before the next heartbeat lands. Treat these phases as live
    # until the overall request exceeds a conservative hard timeout instead of
    # using a short active-phase window that causes false watchdog kills.
    effective_hard_timeout = max(args.hard_timeout, 1800)

    if progress_age <= args.heartbeat_ttl:
        status = "progress_fresh"
    elif phase in prefill_phases and phase_age <= args.prefill_timeout:
        status = "phase_active"
    elif phase in active_inference_phases and request_age < effective_hard_timeout:
        status = "phase_active"
    elif request_age >= effective_hard_timeout:
        status = "hard_timeout"
    elif heartbeat_age <= args.heartbeat_ttl:
        status = "heartbeat_fresh"
    else:
        status = "stale"

    sys.stdout.write(
        f"{status}\t{request_id}\t{request_age}\t{heartbeat_age}\t{phase}\t{progress_age}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
