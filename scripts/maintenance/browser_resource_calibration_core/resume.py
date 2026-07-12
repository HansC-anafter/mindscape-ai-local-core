"""Replay immutable workload evidence into formal quota summaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence import canonical_json
from .run_summary import build_run_summary


def _validated_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"resume evidence row {line_number} must be an object")
        digest = str(raw.pop("evidence_sha256", ""))
        expected = hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()
        if not digest or digest != expected:
            raise ValueError(f"resume evidence hash mismatch at row {line_number}")
        rows.append(raw)
    return rows


def load_run_summaries(
    path: Path,
    *,
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = _validated_rows(path)
    summaries: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    prelaunch_node: dict[str, Any] | None = None
    active: dict[str, Any] | None = None

    def finalize(*, incomplete: bool = False) -> None:
        nonlocal active
        if active is None:
            return
        failures = list(active["failures"])
        if incomplete:
            failures.append("resume_incomplete_evidence")
        summaries.append(
            build_run_summary(
                workload=active["workload"],
                task_id=active["task_id"],
                baseline=baseline,
                prelaunch_node=active["prelaunch_node"],
                node_samples=active["node_samples"],
                terminal_task=active["terminal_task"],
                failures=failures,
            )
        )
        active = None

    for row in rows:
        kind = str(row.get("kind") or "")
        if kind == "idle_cgroup_reset_ready":
            prelaunch_node = row
            continue
        if kind == "natural_claim_observed":
            finalize(incomplete=not bool(active and active["terminal_task"]))
            task = row.get("task") or {}
            task_id = str(task.get("id") or "")
            workload = row.get("classification") or {}
            if not task_id or task_id in seen_task_ids:
                raise ValueError("resume evidence contains missing or duplicate task id")
            for field in (
                "envelope_id",
                "workload_code",
                "partition",
                "repetition",
                "payload_sha256",
            ):
                if workload.get(field) in (None, ""):
                    raise ValueError(f"resume classification missing {field}")
            seen_task_ids.add(task_id)
            active = {
                "task_id": task_id,
                "workload": workload,
                "prelaunch_node": prelaunch_node,
                "node_samples": [],
                "terminal_task": {},
                "failures": [],
            }
            continue
        if active is None or str(row.get("task_id") or "") != active["task_id"]:
            continue
        if kind == "workload_node":
            active["failures"].extend(str(value) for value in row.get("failures") or [])
            if row.get("captured_at_epoch") is not None and row.get(
                "browser_container_working_set_bytes"
            ) is not None:
                active["node_samples"].append(row)
        elif kind == "workload_pool":
            active["failures"].extend(str(value) for value in row.get("failures") or [])
            task = row.get("task") or {}
            if task:
                active["terminal_task"] = task
    finalize(incomplete=not bool(active and active["terminal_task"]))
    return summaries, source_sha256


__all__ = ["load_run_summaries"]
