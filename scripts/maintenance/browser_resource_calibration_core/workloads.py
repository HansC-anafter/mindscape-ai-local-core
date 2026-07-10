"""Natural-claim calibration manifest and quota policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .envelope_classifier import APPROVED_ENVELOPES


def load_workload_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 2:
        raise ValueError("natural-claim manifest version must be 2")
    baseline_summary_path = str(payload.get("baseline_summary_path") or "").strip()
    if not baseline_summary_path:
        raise ValueError("manifest requires baseline_summary_path")
    required = int(payload.get("required_valid_runs_per_envelope") or 0)
    max_browser_local = int(payload.get("max_browser_local_runs") or 0)
    max_captured = int(payload.get("max_captured_post_runs") or 0)
    if required != 3 or max_browser_local != 24 or max_captured != 3:
        raise ValueError("natural-claim quotas must be required=3, browser_local=24, captured=3")
    return {
        "version": 2,
        "baseline_summary_path": baseline_summary_path,
        "required_valid_runs_per_envelope": required,
        "max_browser_local_runs": max_browser_local,
        "max_captured_post_runs": max_captured,
    }


def quota_state(runs: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    valid_counts = {envelope_id: 0 for envelope_id in APPROVED_ENVELOPES}
    partition_runs = {"browser_local": 0, "default_local_browser": 0}
    for run in runs:
        envelope_id = str(run.get("envelope_id") or "")
        partition = str(run.get("partition") or "")
        if partition in partition_runs:
            partition_runs[partition] += 1
        if envelope_id in valid_counts and run.get("valid") is True:
            valid_counts[envelope_id] += 1
    required = int(manifest["required_valid_runs_per_envelope"])
    complete = all(count >= required for count in valid_counts.values())
    failures: list[str] = []
    browser_needed = any(
        valid_counts[envelope_id] < required
        for envelope_id, contract in APPROVED_ENVELOPES.items()
        if contract["partition"] == "browser_local"
    )
    captured_needed = (
        valid_counts["ig_batch_pin_references.captured_posts"] < required
    )
    if browser_needed and partition_runs["browser_local"] >= int(
        manifest["max_browser_local_runs"]
    ):
        failures.append("browser_local_run_limit_reached")
    if captured_needed and partition_runs["default_local_browser"] >= int(
        manifest["max_captured_post_runs"]
    ):
        failures.append("captured_post_run_limit_reached")
    return {
        "complete": complete,
        "failures": failures,
        "valid_counts": valid_counts,
        "partition_runs": partition_runs,
    }


__all__ = ["load_workload_manifest", "quota_state"]
