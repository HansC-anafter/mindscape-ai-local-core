#!/usr/bin/env python3
"""Run artifact result lifecycle maintenance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.services.artifact_lifecycle.maintenance import (
    ArtifactLifecycleMaintenance,
    RuntimeLifecycleApplyGate,
)
from app.services.artifact_lifecycle.manifest_reader import (
    ArtifactLifecycleManifestReader,
)
from app.services.artifact_lifecycle.policy import ArtifactLifecyclePolicy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument("--backup-verified", action="store_true")
    parser.add_argument("--json", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dry_run = not args.apply
    if args.apply and not args.backup_verified:
        raise SystemExit("apply requires --backup-verified")

    archive_dir = args.archive_dir
    if args.apply and archive_dir is None:
        archive_dir = Path("/app/backend/data/maintenance/artifact-lifecycle")

    policy = ArtifactLifecyclePolicy(page_size=args.page_size)
    apply_gate = (
        RuntimeLifecycleApplyGate(
            pgbouncer_admin_url=os.getenv("PGBOUNCER_ADMIN_DATABASE_URL")
        )
        if args.apply
        else None
    )
    runner = ArtifactLifecycleMaintenance(
        reader=ArtifactLifecycleManifestReader(),
        policy=policy,
        apply_gate=apply_gate,
    )
    summary = runner.run(
        dry_run=dry_run,
        limit=args.limit,
        archive_dir=archive_dir,
    )
    print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
