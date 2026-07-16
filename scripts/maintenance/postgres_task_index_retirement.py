#!/usr/bin/env python3
"""Apply one evidence-bound concurrent task-index retirement or backout."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.database.connection_factory import ConnectionFactory  # noqa: E402
from backend.app.runner.db_pool_pressure import sample_pgbouncer_pressure  # noqa: E402
from backend.app.services.runtime_database_incident_gate import (  # noqa: E402
    require_runtime_database_mutation_allowed,
)
from scripts.postgres_task_index_retirement_core import (  # noqa: E402
    collect_database_preflight,
    drop_index,
    evidence_receipt,
    index_manifest_entry,
    observation_window,
    restore_index,
    runtime_gate_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("drop", "restore"))
    parser.add_argument("index_name")
    parser.add_argument("--expected-definition-sha256", required=True)
    parser.add_argument("--runtime-gate-receipt", type=Path, required=True)
    parser.add_argument("--index-manifest-receipt", type=Path, required=True)
    parser.add_argument("--caller-negative-evidence", type=Path, required=True)
    parser.add_argument("--query-plan-evidence", type=Path, required=True)
    parser.add_argument("--workflow-evidence", type=Path, required=True)
    parser.add_argument("--backout-evidence", type=Path, required=True)
    parser.add_argument("--observation-started-at", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    if not args.owner.strip():
        raise ValueError("owner_required")
    runtime_gate_receipt(args.runtime_gate_receipt, now=now)
    manifest, manifest_entry = index_manifest_entry(
        args.index_manifest_receipt,
        index_name=args.index_name,
        expected_definition_sha256=args.expected_definition_sha256,
    )
    evidence = {
        evidence_type: evidence_receipt(
            path,
            evidence_type=evidence_type,
            index_name=args.index_name,
        )
        for evidence_type, path in (
            ("caller_negative_scan", args.caller_negative_evidence),
            ("representative_query_plan", args.query_plan_evidence),
            ("original_workflow_matrix", args.workflow_evidence),
            ("index_backout", args.backout_evidence),
        )
    }
    observation = observation_window(
        observation_started_at=args.observation_started_at,
        stats_reset=manifest.get("stats_reset"),
        now=now,
    )
    operation_kind = "retirement" if args.action == "drop" else "restore"
    operation = f"task_index_{operation_kind}:{args.index_name}"
    require_runtime_database_mutation_allowed(operation)
    factory = ConnectionFactory()
    before = collect_database_preflight(factory, index_name=args.index_name)
    first_pool = sample_pgbouncer_pressure()
    if first_pool.paused:
        raise ValueError(f"pgbouncer_first_sample:{first_pool.reason}")
    time.sleep(5)
    second_pool = sample_pgbouncer_pressure()
    if second_pool.paused:
        raise ValueError(f"pgbouncer_second_sample:{second_pool.reason}")
    mutation = "preflight_only"
    if args.apply:
        if args.action == "drop":
            drop_index(
                factory,
                index_name=args.index_name,
                expected_sha256=args.expected_definition_sha256,
            )
        else:
            backout = evidence["index_backout"]
            restore_index(
                factory,
                index_name=args.index_name,
                definition=str(backout.get("definition") or ""),
                expected_sha256=args.expected_definition_sha256,
            )
        mutation = args.action
    after = collect_database_preflight(factory, index_name=args.index_name)
    if args.apply and args.action == "drop" and after["definition"] is not None:
        raise RuntimeError("index_drop_not_visible")
    if (
        args.apply
        and args.action == "restore"
        and after["definition_sha256"] != args.expected_definition_sha256
    ):
        raise RuntimeError("index_restore_definition_mismatch")
    payload: dict[str, object] = {
        "ok": True,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "action": args.action,
        "mutation": mutation,
        "index_name": args.index_name,
        "owner": args.owner,
        "manifest_entry": manifest_entry,
        "observation": observation,
        "evidence": evidence,
        "before": before,
        "after": after,
        "pgbouncer_samples": [asdict(first_pool), asdict(second_pool)],
    }
    _write(args.receipt, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
