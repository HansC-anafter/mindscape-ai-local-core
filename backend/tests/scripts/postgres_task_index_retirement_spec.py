from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.postgres_task_index_retirement_core.policy import (
    evidence_receipt,
    observation_window,
    runtime_gate_receipt,
)


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_gate_requires_exact_unchanged_thresholds_and_fresh_receipt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.json"
    _write(
        path,
        {
            "ok": True,
            "failures": [],
            "thresholds": {
                "running_observation_limit": 100,
                "pending_observation_limit": 1000,
                "max_postgres_cpu": 200.0,
                "max_runner_cpu_ratio": 0.90,
                "runner_cpu_sample_count": 5,
                "runner_cpu_sustained_sample_count": 3,
                "runner_cpu_sample_interval_seconds": 2.0,
                "max_endpoint_seconds": 5.0,
            },
            "runner_capacity": {"aggregate_max_inflight": 8},
        },
    )
    now = datetime.now(timezone.utc)

    assert runtime_gate_receipt(path, now=now)["ok"] is True
    stale = now.timestamp() - 66
    os.utime(path, (stale, stale))
    with pytest.raises(ValueError, match="stale"):
        runtime_gate_receipt(path, now=now)


def test_observation_rejects_short_or_reset_window() -> None:
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="below_24"):
        observation_window(
            observation_started_at=(now - timedelta(hours=23)).isoformat(),
            stats_reset=None,
            now=now,
        )
    with pytest.raises(ValueError, match="reset_inside"):
        observation_window(
            observation_started_at=(now - timedelta(hours=25)).isoformat(),
            stats_reset=(now - timedelta(hours=2)).isoformat(),
            now=now,
        )


def test_evidence_is_exact_index_typed_and_source_bound(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    _write(
        path,
        {
            "ok": True,
            "evidence_type": "caller_negative_scan",
            "index_name": "idx_tasks_ig_active_workbench",
            "source_commit": "abc123",
        },
    )

    assert evidence_receipt(
        path,
        evidence_type="caller_negative_scan",
        index_name="idx_tasks_ig_active_workbench",
    )["ok"] is True
    with pytest.raises(ValueError, match="index_mismatch"):
        evidence_receipt(
            path,
            evidence_type="caller_negative_scan",
            index_name="idx_tasks_ig_failed_workbench",
        )
