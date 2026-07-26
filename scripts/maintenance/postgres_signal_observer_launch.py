#!/usr/bin/env python3
"""Launch only the preflight-approved PostgreSQL observer, without dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVER_SERVICE = "postgres-signal-observer"
COMPOSE_START_TIMEOUT_SECONDS = 90
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_COMMIT = re.compile(r"^[0-9a-f]{8,64}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-receipt", type=Path, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-digest", required=True)
    return parser


def _load_terminal_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("observer_terminal_receipt_unavailable") from exc
    if type(payload) is not dict:
        raise ValueError("observer_terminal_receipt_invalid")
    return payload


def _validate_terminal_receipt(
    receipt: dict[str, Any],
    *,
    artifact_sha256: str,
    source_commit: str,
) -> None:
    if (
        receipt.get("phase") != "terminal"
        or receipt.get("gate_pass") is not True
        or receipt.get("mutation_permit") is not True
        or receipt.get("failures") != []
        or receipt.get("artifact_sha256") != artifact_sha256
    ):
        raise ValueError("observer_terminal_receipt_not_passed")
    checks = receipt.get("checks")
    decision = checks.get("incident_decision") if type(checks) is dict else None
    details = decision.get("details") if type(decision) is dict else None
    if (
        type(decision) is not dict
        or decision.get("allowed") is not True
        or decision.get("reason") != "incident_diagnostic_permit"
        or type(details) is not dict
        or details.get("source_commit") != source_commit
    ):
        raise ValueError("observer_terminal_receipt_permit_mismatch")
    try:
        expires_at = datetime.fromisoformat(
            str(details.get("expires_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("observer_terminal_receipt_expired") from exc
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
        raise ValueError("observer_terminal_receipt_expired")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not _SHA256.fullmatch(args.artifact_sha256):
        raise SystemExit("observer_artifact_sha256_invalid")
    if not _SOURCE_COMMIT.fullmatch(args.source_commit):
        raise SystemExit("observer_source_commit_invalid")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_digest):
        raise SystemExit("observer_image_digest_invalid")
    try:
        receipt = _load_terminal_receipt(args.terminal_receipt)
        _validate_terminal_receipt(
            receipt,
            artifact_sha256=args.artifact_sha256,
            source_commit=args.source_commit,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    environment = {
        **os.environ,
        "POSTGRES_SIGNAL_OBSERVER_ARTIFACT_SHA256": args.artifact_sha256,
        "POSTGRES_SIGNAL_OBSERVER_SOURCE_COMMIT": args.source_commit,
        "POSTGRES_SIGNAL_OBSERVER_IMAGE_DIGEST": args.image_digest,
    }
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(REPO_ROOT),
        "--profile",
        "runtime-db-observer",
        "up",
        "-d",
        "--no-deps",
        OBSERVER_SERVICE,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=COMPOSE_START_TIMEOUT_SECONDS,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                {
                    "service": OBSERVER_SERVICE,
                    "started": False,
                    "dependency_reconciliation": False,
                    "compose_start_timed_out": True,
                    "runtime_state_unknown": True,
                    "timeout_seconds": COMPOSE_START_TIMEOUT_SECONDS,
                },
                sort_keys=True,
            )
        )
        return 2
    result = {
        "service": OBSERVER_SERVICE,
        "started": completed.returncode == 0,
        "dependency_reconciliation": False,
        "compose_start_timed_out": False,
        "runtime_state_unknown": False,
        "returncode": completed.returncode,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if completed.returncode == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
