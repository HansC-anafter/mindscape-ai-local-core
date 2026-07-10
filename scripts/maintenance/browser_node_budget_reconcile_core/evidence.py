"""Validate long-window single-runner evidence and derive reconciliation bytes."""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.maintenance.browser_resource_calibration_core.evidence import (
    canonical_json,
)
from scripts.maintenance.browser_resource_calibration_core.parsing import (
    round_request_bytes,
)


@dataclass(frozen=True)
class ReconciliationEvidence:
    task_id: str
    envelope_id: str
    runner_id: str
    runner_container: str
    sample_count: int
    duration_seconds: float
    cadence_median_seconds: float
    cadence_max_seconds: float
    observed_cgroup_peak_bytes: int
    request_bytes: int
    evidence_fingerprint: str
    pool_sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validated_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw_bytes = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(raw_bytes.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_json_line:{line_number}") from exc
        observed = str(row.pop("evidence_sha256", ""))
        expected = hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()
        if observed != expected:
            raise ValueError(f"evidence_hash_mismatch:{line_number}")
        row["evidence_sha256"] = observed
        rows.append(row)
    if not rows:
        raise ValueError("evidence_empty")
    return rows, hashlib.sha256(raw_bytes).hexdigest()


def _claim_identity(
    rows: list[dict[str, Any]],
    *,
    task_id: str,
) -> tuple[str, str]:
    claims = [
        row
        for row in rows
        if row.get("kind") == "natural_claim_observed"
        and str((row.get("task") or {}).get("id") or "") == task_id
    ]
    if len(claims) != 1:
        raise ValueError("natural_claim_identity_not_unique")
    claim = claims[0]
    classification = claim.get("classification") or {}
    if classification.get("valid") is not True:
        raise ValueError("natural_claim_classification_invalid")
    runner_id = str((claim.get("task") or {}).get("runner_id") or "")
    envelope_id = str(classification.get("envelope_id") or "")
    if not runner_id or not envelope_id:
        raise ValueError("natural_claim_identity_incomplete")
    return runner_id, envelope_id


def validate_reconciliation_evidence(
    path: Path,
    *,
    task_id: str,
    runner_container: str,
    minimum_samples: int = 720,
    minimum_duration_seconds: float = 3600.0,
) -> ReconciliationEvidence:
    rows, fingerprint = _validated_rows(path)
    runner_id, envelope_id = _claim_identity(rows, task_id=task_id)
    node_rows = [
        row
        for row in rows
        if row.get("kind") == "workload_node"
        and str(row.get("task_id") or "") == task_id
        and str(row.get("envelope_id") or "") == envelope_id
    ]
    if len(node_rows) < minimum_samples:
        raise ValueError("node_sample_count_below_minimum")
    node_rows.sort(key=lambda row: float(row["captured_at_epoch"]))
    segments: list[list[dict[str, Any]]] = []
    segment: list[dict[str, Any]] = []
    for row in node_rows:
        epoch = float(row["captured_at_epoch"])
        if segment and epoch - float(segment[-1]["captured_at_epoch"]) > 10.0:
            segments.append(segment)
            segment = []
        segment.append(row)
    if segment:
        segments.append(segment)
    qualifying = [
        candidate
        for candidate in segments
        if len(candidate) >= minimum_samples
        and float(candidate[-1]["captured_at_epoch"])
        - float(candidate[0]["captured_at_epoch"])
        >= minimum_duration_seconds
    ]
    if not qualifying:
        raise ValueError("continuous_evidence_window_unavailable")
    node_rows = max(
        qualifying,
        key=lambda candidate: (
            float(candidate[-1]["captured_at_epoch"])
            - float(candidate[0]["captured_at_epoch"]),
            len(candidate),
        ),
    )
    epochs = [float(row["captured_at_epoch"]) for row in node_rows]
    duration = epochs[-1] - epochs[0]
    if duration < minimum_duration_seconds:
        raise ValueError("evidence_duration_below_minimum")
    deltas = [later - earlier for earlier, later in zip(epochs, epochs[1:])]
    cadence_median = statistics.median(deltas)
    cadence_max = max(deltas)
    if not 4.0 <= cadence_median <= 6.0 or cadence_max > 10.0:
        raise ValueError("node_cadence_invalid")

    peaks: list[int] = []
    for row in node_rows:
        matching = [
            item
            for item in row.get("browser_cgroups") or []
            if str(item.get("container") or "") == runner_container
        ]
        if len(matching) != 1:
            raise ValueError("runner_cgroup_identity_not_unique")
        cgroup = matching[0]
        if any(
            int(cgroup.get(key) or 0) != 0
            for key in ("oom_kill", "oom_group_kill")
        ):
            raise ValueError("runner_cgroup_oom_observed")
        peak = int(cgroup.get("memory_peak_bytes") or 0)
        if peak <= 0:
            raise ValueError("runner_cgroup_peak_unavailable")
        peaks.append(peak)

    pool_rows = [
        row
        for row in rows
        if row.get("kind") == "workload_pool"
        and str(row.get("task_id") or "") == task_id
        and str(row.get("envelope_id") or "") == envelope_id
        and epochs[0] <= float(row.get("captured_at_epoch") or 0) <= epochs[-1]
    ]
    if not pool_rows:
        raise ValueError("pool_evidence_missing")
    for row in pool_rows:
        task = row.get("task") or {}
        if str(task.get("id") or "") != task_id or task.get("status") != "running":
            raise ValueError("pool_task_not_running")
        if row.get("failures"):
            raise ValueError("pool_collector_failure")
        if str(row.get("postgres") or "") != "f|off":
            raise ValueError("postgres_not_writable")
        for pool in row.get("pgbouncer_pools") or []:
            if int(pool.get("cl_waiting") or 0) != 0 or int(pool.get("maxwait") or 0) != 0:
                raise ValueError("pgbouncer_wait_observed")

    observed_peak = max(peaks)
    return ReconciliationEvidence(
        task_id=task_id,
        envelope_id=envelope_id,
        runner_id=runner_id,
        runner_container=runner_container,
        sample_count=len(node_rows),
        duration_seconds=duration,
        cadence_median_seconds=cadence_median,
        cadence_max_seconds=cadence_max,
        observed_cgroup_peak_bytes=observed_peak,
        request_bytes=round_request_bytes(observed_peak),
        evidence_fingerprint=fingerprint,
        pool_sample_count=len(pool_rows),
    )
