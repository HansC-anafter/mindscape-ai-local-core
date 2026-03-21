#!/usr/bin/env python3
"""
Backfill IG reference analysis_debug metadata from historical task payloads.

Default mode is dry-run. Use --apply to persist metadata changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
for _path in (BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from sqlalchemy import bindparam, text

from app.database.engine import engine_postgres_core
from capabilities.ig.models.reference_metadata import ReferenceMetadata
from capabilities.ig.services.reference_index import ReferenceIndex
from capabilities.ig.services.workspace_storage import WorkspaceStorage
from capabilities.ig.tools.ig_analyze_reference import (
    capture_analysis_debug,
    extract_thinking_text,
)


TASK_QUERY = text(
    """
    SELECT
        id,
        created_at,
        COALESCE(
            execution_context::jsonb #>> '{inputs,reference_id}',
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,preprocess,reference_id}',
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,backfill,reference_id}'
        ) AS reference_id,
        COALESCE(
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,vision_analyze,results,0,shortcode}',
            execution_context::jsonb #>> '{workflow_result,step_outputs,vision_analyze,results,0,shortcode}'
        ) AS shortcode,
        COALESCE(
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,vision_analyze,results,0,description}',
            execution_context::jsonb #>> '{workflow_result,step_outputs,vision_analyze,results,0,description}'
        ) AS description,
        COALESCE(
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,vision_analyze,results,0,thinking}',
            execution_context::jsonb #>> '{workflow_result,step_outputs,vision_analyze,results,0,thinking}'
        ) AS thinking
    FROM tasks
    WHERE workspace_id = :workspace_id
      AND pack_id = 'ig_analyze_pinned_reference'
      AND status = 'succeeded'
      AND execution_context IS NOT NULL
      AND (
        COALESCE(
            execution_context::jsonb #>> '{inputs,reference_id}',
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,preprocess,reference_id}',
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,backfill,reference_id}'
        ) IN :reference_ids
        OR COALESCE(
            execution_context::jsonb #>> '{workflow_result,context,ig_analyze_pinned_reference,vision_analyze,results,0,shortcode}',
            execution_context::jsonb #>> '{workflow_result,step_outputs,vision_analyze,results,0,shortcode}'
        ) IN :shortcodes
      )
    ORDER BY created_at DESC, id DESC
    """
).bindparams(
    bindparam("reference_ids", expanding=True),
    bindparam("shortcodes", expanding=True),
)


@dataclass
class HistoricalTaskPayload:
    task_id: str
    reference_id: str
    shortcode: str
    raw_text: str
    thinking_text: str


@dataclass
class BackfillCandidate:
    metadata_path: Path
    metadata: ReferenceMetadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill IG analysis_debug metadata from historical tasks"
    )
    parser.add_argument("--workspace-id", required=True, help="Target workspace ID")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N missing references",
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
        help="How many sample updates to print in the summary",
    )
    return parser.parse_args()


def _iter_metadata_files(refs_path: Path) -> Iterable[Path]:
    for child in refs_path.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("_") and child.name != "_unsorted":
            continue
        for json_file in child.glob("*.json"):
            if json_file.name.startswith("_"):
                continue
            yield json_file


def _has_existing_thinking(meta: ReferenceMetadata) -> bool:
    debug_thinking = ""
    if meta.analysis_debug is not None:
        debug_thinking = (meta.analysis_debug.thinking_text or "").strip()
    mirror_thinking = ""
    if isinstance(meta.vision_description, dict):
        mirror_thinking = (meta.vision_description.get("_thinking") or "").strip()
    return bool(debug_thinking or mirror_thinking)


def _collect_backfill_candidates(refs_path: Path) -> list[BackfillCandidate]:
    missing: list[BackfillCandidate] = []
    for metadata_path in _iter_metadata_files(refs_path):
        try:
            meta = ReferenceMetadata.from_json(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.vision_description is None:
            continue
        if _has_existing_thinking(meta):
            continue
        missing.append(BackfillCandidate(metadata_path=metadata_path, metadata=meta))
    missing.sort(
        key=lambda item: (
            item.metadata.source_handle or "",
            item.metadata.source_shortcode or "",
            item.metadata.reference_id,
        )
    )
    return missing


def _payload_from_metadata(meta: ReferenceMetadata) -> HistoricalTaskPayload | None:
    debug = meta.analysis_debug
    if debug is None or not (debug.raw_text or "").strip():
        return None
    thinking_text = extract_thinking_text(
        raw_text=debug.raw_text,
        thinking_text=debug.thinking_text or "",
    )
    return HistoricalTaskPayload(
        task_id="metadata",
        reference_id=meta.reference_id,
        shortcode=(meta.source_shortcode or "").strip(),
        raw_text=debug.raw_text,
        thinking_text=thinking_text,
    )


def _load_historical_payloads(
    workspace_id: str,
    reference_ids: list[str],
    shortcodes: list[str],
) -> tuple[dict[str, HistoricalTaskPayload], dict[str, HistoricalTaskPayload], int]:
    if engine_postgres_core is None:
        raise RuntimeError("PostgreSQL core engine is not initialized")

    reference_ids = [value for value in reference_ids if value]
    shortcodes = [value for value in shortcodes if value]
    if not reference_ids and not shortcodes:
        return {}, {}, 0

    by_shortcode: dict[str, HistoricalTaskPayload] = {}
    by_reference_id: dict[str, HistoricalTaskPayload] = {}

    with engine_postgres_core.connect() as conn:
        rows = conn.execute(
            TASK_QUERY,
            {
                "workspace_id": workspace_id,
                "reference_ids": reference_ids or ["__missing__"],
                "shortcodes": shortcodes or ["__missing__"],
            },
        ).mappings().all()

    for row in rows:
        raw_text = row["description"] or ""
        thinking_text = extract_thinking_text(
            raw_text=raw_text,
            thinking_text=row["thinking"] or "",
        )
        payload = HistoricalTaskPayload(
            task_id=str(row["id"]),
            reference_id=(row["reference_id"] or "").strip(),
            shortcode=(row["shortcode"] or "").strip(),
            raw_text=raw_text,
            thinking_text=thinking_text,
        )
        if payload.shortcode and payload.shortcode not in by_shortcode:
            by_shortcode[payload.shortcode] = payload
        if payload.reference_id and payload.reference_id not in by_reference_id:
            by_reference_id[payload.reference_id] = payload

    return by_shortcode, by_reference_id, len(rows)


def _to_summary_dict(payload: HistoricalTaskPayload, meta: ReferenceMetadata, match_type: str) -> dict[str, Any]:
    return {
        "reference_id": meta.reference_id,
        "shortcode": meta.source_shortcode,
        "task_id": payload.task_id,
        "match_type": match_type,
        "raw_chars": len(payload.raw_text),
        "thinking_chars": len(payload.thinking_text),
    }


def main() -> int:
    args = parse_args()

    storage = WorkspaceStorage(args.workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)

    missing_refs = _collect_backfill_candidates(refs_path)
    if args.limit is not None:
        missing_refs = missing_refs[: args.limit]

    task_lookup_candidates = [
        item
        for item in missing_refs
        if _payload_from_metadata(item.metadata) is None
    ]
    by_shortcode, by_reference_id, task_row_count = _load_historical_payloads(
        args.workspace_id,
        reference_ids=[item.metadata.reference_id for item in task_lookup_candidates],
        shortcodes=[(item.metadata.source_shortcode or "").strip() for item in task_lookup_candidates],
    )

    summary: dict[str, Any] = {
        "workspace_id": args.workspace_id,
        "apply": args.apply,
        "task_rows_scanned": task_row_count,
        "missing_refs_scanned": len(missing_refs),
        "matched_by_metadata": 0,
        "matched": 0,
        "matched_by_shortcode": 0,
        "matched_by_reference_id": 0,
        "updated": 0,
        "updated_with_thinking": 0,
        "updated_with_thinking_mirror": 0,
        "skipped_no_task": 0,
        "skipped_empty_raw": 0,
        "sample_updates": [],
    }

    for item in missing_refs:
        meta = item.metadata
        match = _payload_from_metadata(meta)
        match_type = "metadata" if match is not None else ""

        if match is None:
            match_type = ""
            shortcode = (meta.source_shortcode or "").strip()
            if shortcode:
                match = by_shortcode.get(shortcode)
                if match:
                    match_type = "shortcode"

        if match is None:
            match = by_reference_id.get(meta.reference_id)
            if match:
                match_type = "reference_id"

        if match is None:
            summary["skipped_no_task"] += 1
            continue

        summary["matched"] += 1
        summary[f"matched_by_{match_type}"] += 1

        if not match.raw_text:
            summary["skipped_empty_raw"] += 1
            continue

        if len(summary["sample_updates"]) < args.sample_limit:
            summary["sample_updates"].append(_to_summary_dict(match, meta, match_type))

        if not args.apply:
            continue

        refreshed_debug = capture_analysis_debug(
            raw_text=match.raw_text,
            thinking_text=match.thinking_text,
        )
        if meta.analysis_debug is not None:
            refreshed_debug.failure_stage = meta.analysis_debug.failure_stage
            refreshed_debug.failure_reason = meta.analysis_debug.failure_reason
            refreshed_debug.captured_at = meta.analysis_debug.captured_at or refreshed_debug.captured_at
        meta.analysis_debug = refreshed_debug

        if match.thinking_text and isinstance(meta.vision_description, dict):
            if not meta.vision_description.get("_thinking"):
                meta.vision_description["_thinking"] = match.thinking_text
                summary["updated_with_thinking_mirror"] += 1

        item.metadata_path.write_text(meta.to_json(), encoding="utf-8")
        summary["updated"] += 1
        if match.thinking_text:
            summary["updated_with_thinking"] += 1

    if args.apply and summary["updated"] > 0:
        index.rebuild()

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
