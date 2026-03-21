#!/usr/bin/env python3
"""
Reset stale IG reference analysis jobs back to PENDING.

Default mode is dry-run. Use --apply to persist metadata and index updates.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
for _path in (BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from capabilities.ig.models.reference_metadata import ReferenceMetadata
from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.workspace_storage import WorkspaceStorage
from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file


@dataclass
class ResetCandidate:
    reference_id: str
    metadata_path: Path
    metadata: ReferenceMetadata
    age_minutes: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset stale IG reference jobs from RUNNING back to PENDING"
    )
    parser.add_argument("--workspace-id", required=True, help="Target workspace ID")
    parser.add_argument(
        "--older-than-minutes",
        type=int,
        default=30,
        help="Only reset RUNNING jobs older than this many minutes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N matching jobs",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist metadata updates. Default is dry-run.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="How many sample candidates to print",
    )
    return parser.parse_args()


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _resolve_metadata_path(
    refs_path: Path,
    reference_id: str,
    entry: dict[str, object],
    index: ReferenceIndex,
) -> Path | None:
    handle = str(entry.get("source_handle") or "").strip()
    shortcode = str(entry.get("source_shortcode") or "").strip()
    if shortcode:
        if handle and not handle.startswith("_"):
            candidate = refs_path / handle / f"{shortcode}.json"
        else:
            candidate = refs_path / "_unsorted" / f"{shortcode}.json"
        if candidate.exists():
            return candidate
    return _find_metadata_file(refs_path, reference_id, index)


def _iter_candidates(
    workspace_id: str,
    *,
    older_than_minutes: int,
) -> tuple[list[ResetCandidate], int]:
    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)
    index_data = index._read_index()
    entries = index_data.get("entries", {})
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=older_than_minutes)

    candidates: list[ResetCandidate] = []
    running_total = 0
    for reference_id, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("analysis_status", "")).strip().upper()
        if status != "RUNNING":
            continue
        running_total += 1
        started_at = _parse_timestamp(
            entry.get("started_at")
            or entry.get("pending_sort_at")
            or entry.get("queued_at")
        )
        if started_at is None or started_at > cutoff:
            continue
        metadata_path = _resolve_metadata_path(refs_path, reference_id, entry, index)
        if not metadata_path or not metadata_path.exists():
            continue
        try:
            metadata = ReferenceMetadata.from_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except Exception:
            continue
        if metadata.analysis_job is None:
            continue
        if str(metadata.analysis_job.status).strip().upper() != "RUNNING":
            continue
        age_minutes = (now - started_at).total_seconds() / 60.0
        candidates.append(
            ResetCandidate(
                reference_id=reference_id,
                metadata_path=metadata_path,
                metadata=metadata,
                age_minutes=age_minutes,
            )
        )
    candidates.sort(key=lambda item: (-item.age_minutes, item.reference_id))
    return candidates, running_total


def _apply_reset(candidates: Iterable[ResetCandidate], workspace_id: str) -> int:
    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)
    updated = 0
    for candidate in candidates:
        job = candidate.metadata.analysis_job
        if job is None:
            continue
        job.queue()
        candidate.metadata_path.write_text(
            candidate.metadata.to_json(),
            encoding="utf-8",
        )
        index.add_entry(candidate.reference_id, candidate.metadata.model_dump())
        updated += 1
    return updated


def main() -> int:
    args = parse_args()
    candidates, running_total = _iter_candidates(
        args.workspace_id,
        older_than_minutes=args.older_than_minutes,
    )
    if args.limit is not None:
        candidates = candidates[: args.limit]

    print(
        f"workspace={args.workspace_id} running_total={running_total} "
        f"stale_candidates={len(candidates)} timeout_minutes={args.older_than_minutes}"
    )
    for candidate in candidates[: args.sample_limit]:
        print(
            f"- {candidate.reference_id} "
            f"{candidate.metadata.source_handle} "
            f"{candidate.metadata.source_shortcode} "
            f"age={candidate.age_minutes:.1f}m "
            f"path={candidate.metadata_path}"
        )

    if not args.apply:
        print("dry_run=true")
        return 0

    updated = _apply_reset(candidates, args.workspace_id)
    print(f"dry_run=false updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
