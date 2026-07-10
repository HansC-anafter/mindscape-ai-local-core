"""Calibration workload manifest and sequential launch policy."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any

from .evidence import canonical_json
from .http_client import APPROVED_WORKLOADS


def load_workload_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("workload manifest version must be 1")
    workspace_id = str(payload.get("workspace_id") or "").strip()
    baseline_summary_path = str(payload.get("baseline_summary_path") or "").strip()
    workloads = payload.get("workloads")
    if not workspace_id or not baseline_summary_path or not isinstance(workloads, list):
        raise ValueError("manifest requires workspace, baseline summary, and workloads")
    codes = [str(item.get("workload_code") or "") for item in workloads if isinstance(item, dict)]
    if len(workloads) != 3 or set(codes) != APPROVED_WORKLOADS:
        raise ValueError("manifest requires exactly the three approved workloads")
    normalized: list[dict[str, Any]] = []
    for item in workloads:
        if not isinstance(item, dict) or not isinstance(item.get("inputs"), dict):
            raise ValueError("each workload requires an inputs object")
        inputs = item["inputs"]
        if str(inputs.get("workspace_id") or workspace_id) != workspace_id:
            raise ValueError("workload workspace must match manifest workspace")
        workload_code = str(item["workload_code"])
        normalized.append(
            {
                "workload_code": workload_code,
                "inputs": dict(inputs),
                "payload_sha256": hashlib.sha256(
                    canonical_json(inputs).encode("utf-8")
                ).hexdigest(),
            }
        )
    return {
        "version": 1,
        "workspace_id": workspace_id,
        "profile_id": str(payload.get("profile_id") or "default-user"),
        "baseline_summary_path": baseline_summary_path,
        "workloads": normalized,
    }


def build_run_sequence(manifest: dict[str, Any], repetitions: int) -> list[dict[str, Any]]:
    if repetitions != 3:
        raise ValueError("formal calibration requires exactly three repetitions")
    sequence: list[dict[str, Any]] = []
    for workload in manifest["workloads"]:
        for repetition in range(1, repetitions + 1):
            sequence.append({**workload, "repetition": repetition})
    return sequence


def build_start_request(
    *,
    api_base: str,
    workspace_id: str,
    profile_id: str,
    workload: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "playbook_code": workload["workload_code"],
            "workspace_id": workspace_id,
            "profile_id": profile_id,
            "execution_backend": "runner",
            "auto_execute": "true",
        }
    )
    url = f"{api_base.rstrip('/')}/api/v1/playbooks/execute/start?{query}"
    return url, {
        "inputs": dict(workload["inputs"]),
        "auto_execute": True,
        "execution_backend": "runner",
    }
