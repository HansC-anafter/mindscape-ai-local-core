"""Shared support helpers for queue utilization snapshots."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


SNAPSHOT_WRITER_LEASE_KEY = "mindscape:runner_queue_utilization:snapshot_writer"
SNAPSHOT_WRITER_LEASE_SECONDS = 55
SNAPSHOT_RETENTION_DAYS = 14
MAX_VISIBLE_SCAN_LIMIT = 128


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def _datetime_from_epoch(epoch: float) -> datetime:
    return datetime.fromtimestamp(float(epoch), timezone.utc)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_task_id(raw_value: object) -> str:
    if isinstance(raw_value, bytes):
        return raw_value.decode()
    return str(raw_value)


def _clamped_scan_limit(value: int | None = None) -> int:
    if value is None:
        value = _to_int(
            os.getenv("LOCAL_CORE_RUNNER_PLAYBOOK_FAIR_SCAN_LIMIT"),
            MAX_VISIBLE_SCAN_LIMIT,
        )
    return max(
        1,
        min(_to_int(value, MAX_VISIBLE_SCAN_LIMIT), MAX_VISIBLE_SCAN_LIMIT),
    )
