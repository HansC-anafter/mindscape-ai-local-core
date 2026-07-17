#!/usr/bin/env python3
"""Append-only collector and fail-closed evaluator for the 72-hour soak."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.postgres_soak_core import REQUIRED_WORKLOADS, evaluate_soak  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _paths(root: Path) -> tuple[Path, Path, Path]:
    return root / "metadata.json", root / "samples.jsonl", root / "workloads.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "sample", "record-workload", "status", "finalize"])
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--workload", choices=sorted(REQUIRED_WORKLOADS))
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    metadata_path, samples_path, workloads_path = _paths(args.evidence_dir)

    if args.command == "start":
        if metadata_path.exists():
            raise RuntimeError("soak_already_started")
        metadata_path.write_text(
            json.dumps({"started_at": _now(), "stats_reset": False}, indent=2) + "\n",
            encoding="utf-8",
        )
        workloads_path.write_text("[]\n", encoding="utf-8")
        return 0
    if not metadata_path.exists():
        raise RuntimeError("soak_not_started")
    if args.command == "sample":
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/maintenance/runtime_pressure_gate.py")],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
        payload["captured_at"] = _now()
        payload["ok"] = result.returncode == 0 and bool(payload.get("ok"))
        with samples_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return 0 if payload["ok"] else 2
    if args.command == "record-workload":
        if not args.workload:
            raise RuntimeError("workload_required")
        workloads = set(json.loads(workloads_path.read_text(encoding="utf-8")))
        workloads.add(args.workload)
        workloads_path.write_text(
            json.dumps(sorted(workloads), indent=2) + "\n",
            encoding="utf-8",
        )
        return 0

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    samples = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
    ] if samples_path.exists() else []
    workloads = json.loads(workloads_path.read_text(encoding="utf-8"))
    verdict = evaluate_soak(
        started_at=metadata["started_at"],
        now=_now(),
        samples=samples,
        workloads=workloads,
    )
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if verdict["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
