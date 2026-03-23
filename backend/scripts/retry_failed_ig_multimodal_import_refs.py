#!/usr/bin/env python3
"""
Requeue IG reference analyses that failed due to the historical
core_llm.multimodal import/backend mismatch.

Default mode is dry-run. Use --apply to persist metadata/index updates
and enqueue fresh ig_analyze_pinned_reference tasks.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
for _path in (BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from app.database.config import get_engine_kwargs, get_postgres_url_core
from capabilities.ig.models.reference_metadata import ReferenceMetadata
from capabilities.ig.services.auto_analyze import enqueue_reference_analysis
from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.workspace_storage import WorkspaceStorage
from capabilities.ig.tools.ig_analyze_reference import _find_metadata_file


ERROR_FILTER_SQL = """
(
    COALESCE(error, '') ILIKE '%backend.app.capabilities.core_llm.services.multimodal%'
    OR COALESCE(error, '') ILIKE '%core_llm.multimodal_analyze%'
)
"""


@dataclass(frozen=True)
class RetryCandidate:
    workspace_id: str
    reference_id: str
    analysis_profile: str
    failed_task_id: str
    created_at: str
    error_excerpt: str


@dataclass
class ApplyResult:
    reference_id: str
    execution_id: str | None = None
    status: str = "enqueued"
    reason: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Retry failed IG reference analyses caused by the historical "
            "core_llm.multimodal import/backend mismatch."
        )
    )
    parser.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Only process candidates from these workspace IDs. Repeatable.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="How many dry-run sample rows to print.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N matching candidates after filtering.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist metadata/index updates and enqueue fresh tasks.",
    )
    parser.add_argument(
        "--clear-analysis-debug",
        action="store_true",
        help="Also clear analysis_debug from metadata when retrying.",
    )
    parser.add_argument(
        "--vision-execution-backend",
        default=None,
        help=(
            "Optional explicit backend override for re-enqueued jobs. "
            "Default is to let the current live workspace policy resolve at execute time."
        ),
    )
    parser.add_argument(
        "--vision-target-device-id",
        default=None,
        help="Optional explicit target device for re-enqueued jobs.",
    )
    return parser.parse_args()


def load_candidates(workspace_ids: set[str] | None = None) -> list[RetryCandidate]:
    engine = create_engine(get_postgres_url_core(), **get_engine_kwargs())
    query = text(
        f"""
        SELECT
            workspace_id,
            reference_id,
            analysis_profile,
            failed_task_id,
            created_at,
            error_excerpt
        FROM (
            SELECT
                DISTINCT ON (workspace_id, reference_id)
                workspace_id,
                COALESCE(execution_context->'inputs'->>'reference_id', '') AS reference_id,
                COALESCE(NULLIF(execution_context->'inputs'->>'analysis_profile', ''), 'visual_anatomy') AS analysis_profile,
                id::text AS failed_task_id,
                status,
                created_at,
                LEFT(COALESCE(error, ''), 220) AS error_excerpt
            FROM tasks
            WHERE pack_id = 'ig_analyze_pinned_reference'
              AND COALESCE(execution_context->'inputs'->>'reference_id', '') <> ''
            ORDER BY workspace_id, COALESCE(execution_context->'inputs'->>'reference_id', ''), created_at DESC
        ) latest_refs
        WHERE status = 'failed'
          AND {ERROR_FILTER_SQL.replace("error", "error_excerpt")}
        ORDER BY workspace_id, reference_id
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()

    candidates = [
        RetryCandidate(
            workspace_id=str(row["workspace_id"]),
            reference_id=str(row["reference_id"]),
            analysis_profile=str(row["analysis_profile"] or "visual_anatomy"),
            failed_task_id=str(row["failed_task_id"]),
            created_at=str(row["created_at"]),
            error_excerpt=str(row["error_excerpt"] or ""),
        )
        for row in rows
    ]
    if workspace_ids:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.workspace_id in workspace_ids
        ]
    return candidates


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


def _group_counts(candidates: Iterable[RetryCandidate]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for candidate in candidates:
        counts[candidate.workspace_id][candidate.analysis_profile] += 1
    return counts


def _apply_candidate(
    candidate: RetryCandidate,
    *,
    clear_analysis_debug: bool,
    vision_execution_backend: str | None,
    vision_target_device_id: str | None,
) -> ApplyResult:
    storage = WorkspaceStorage(candidate.workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)
    index_data = index._read_index()
    entries = index_data.get("entries", {})
    entry = entries.get(candidate.reference_id) or {}

    metadata_path = _resolve_metadata_path(refs_path, candidate.reference_id, entry, index)
    if not metadata_path or not metadata_path.exists():
        return ApplyResult(
            reference_id=candidate.reference_id,
            status="skipped",
            reason="metadata_missing",
        )

    metadata = ReferenceMetadata.from_json(metadata_path.read_text(encoding="utf-8"))
    if metadata.analysis_job is None:
        return ApplyResult(
            reference_id=candidate.reference_id,
            status="skipped",
            reason="analysis_job_missing",
        )

    metadata.analysis_job.queue(reset_completed=False)
    metadata.analysis_job.last_error = None
    metadata.analysis_provenance = None
    if clear_analysis_debug:
        metadata.analysis_debug = None

    metadata_path.write_text(metadata.to_json(), encoding="utf-8")
    index.add_entry(candidate.reference_id, metadata.model_dump())

    image_url = str(entry.get("image_url") or metadata.source_url or "").strip()
    execution_id = enqueue_reference_analysis(
        workspace_id=candidate.workspace_id,
        reference_id=candidate.reference_id,
        image_url=image_url,
        source_handle=metadata.source_handle,
        analysis_profile=candidate.analysis_profile,
        parent_execution_id=f"batch-retry-{uuid.uuid4().hex[:8]}",
        vision_execution_backend=vision_execution_backend,
        vision_target_device_id=vision_target_device_id,
    )
    return ApplyResult(
        reference_id=candidate.reference_id,
        execution_id=execution_id,
        status="enqueued" if execution_id else "skipped",
        reason=None if execution_id else "enqueue_returned_none",
    )


def main() -> int:
    args = parse_args()
    workspace_ids = {item.strip() for item in args.workspace_id if str(item).strip()}
    candidates = load_candidates(workspace_ids or None)
    if args.limit is not None:
        candidates = candidates[: args.limit]

    counts = _group_counts(candidates)
    print(
        f"matched_candidates={len(candidates)} "
        f"workspace_filter={sorted(workspace_ids) if workspace_ids else 'ALL'}"
    )
    for workspace_id, profile_counts in sorted(counts.items()):
        summary = ", ".join(
            f"{profile}:{count}" for profile, count in sorted(profile_counts.items())
        )
        print(f"- workspace={workspace_id} profiles=[{summary}]")

    for candidate in candidates[: args.sample_limit]:
        print(
            f"  sample workspace={candidate.workspace_id} "
            f"ref={candidate.reference_id} "
            f"profile={candidate.analysis_profile} "
            f"failed_task={candidate.failed_task_id} "
            f"created_at={candidate.created_at}"
        )

    if not args.apply:
        print("dry_run=true")
        return 0

    results: list[ApplyResult] = []
    for candidate in candidates:
        results.append(
            _apply_candidate(
                candidate,
                clear_analysis_debug=args.clear_analysis_debug,
                vision_execution_backend=args.vision_execution_backend,
                vision_target_device_id=args.vision_target_device_id,
            )
        )

    enqueued = [item for item in results if item.status == "enqueued"]
    skipped = [item for item in results if item.status != "enqueued"]
    print(
        f"dry_run=false total={len(results)} "
        f"enqueued={len(enqueued)} skipped={len(skipped)}"
    )
    for item in skipped[: args.sample_limit]:
        print(
            f"  skipped ref={item.reference_id} status={item.status} reason={item.reason}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
