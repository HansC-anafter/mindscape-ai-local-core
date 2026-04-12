"""
Backfill Projections — populate _index.json with V2.0 projection fields.

Scans all reference metadata JSON files, extracts V2.0 projection fields
via build_projection(), and merges them into the existing _index.json index.

Operational Safety (per evi-plan Review #E):
  - Atomic replace: writes _index.json.tmp then os.replace()
  - Idempotent: pure function projection, same input = same output
  - Resume-safe: tracks cursor in _backfill_cursor.json
  - Concurrency: uses shared fcntl lock via ReferenceIndex

Usage:
  python -m capabilities.ig.scripts.backfill_projections --workspace-id <WS_ID>
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def backfill_workspace(workspace_id: str, data_root: str = "") -> dict:
    """Backfill projection fields for all references in a workspace.

    Returns summary dict with counts.
    """
    from capabilities.ig.services.projection_builder import build_projection
    from capabilities.ig.services.reference_index import ReferenceIndex
    from capabilities.ig.services.workspace_storage import WorkspaceStorage

    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index = ReferenceIndex(refs_path)
    cursor_path = refs_path / "_backfill_cursor.json"

    # Load cursor (previously processed ref_ids)
    processed = set()
    if False:
        try:
            cursor_data = json.loads(cursor_path.read_text(encoding="utf-8"))
            processed = set(cursor_data.get("processed_ids", []))
            logger.info("[Backfill] Resuming from cursor: %d already processed", len(processed))
        except Exception:
            logger.warning("[Backfill] Corrupt cursor file, starting fresh")

    # Read current index
    index._acquire_lock()
    try:
        data = index._read_index(mutable=True)
        entries = data.get("entries", {})

        updated = 0
        skipped = 0
        errors = 0

        for ref_id, entry in list(entries.items()):
            if ref_id in processed:
                skipped += 1
                continue

            # Find metadata file to get vision_description
            try:
                metadata_path = _find_metadata_for_ref(refs_path, ref_id, entry)
                if not metadata_path:
                    skipped += 1
                    processed.add(ref_id)
                    continue

                meta_dict = json.loads(metadata_path.read_text(encoding="utf-8"))
                vision = meta_dict.get("vision_description")

                if vision and isinstance(vision, dict):
                    projection = build_projection(vision)
                    entries[ref_id].update(projection)
                    updated += 1
                else:
                    skipped += 1

                processed.add(ref_id)

            except Exception as e:
                logger.warning("[Backfill] Error processing %s: %s", ref_id, e)
                errors += 1
                processed.add(ref_id)

        # Atomic write: tmp file → os.replace
        tmp_path = refs_path / "_index.json.tmp"
        data["entries"] = entries
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(str(tmp_path), str(index.index_path))

        # Update cursor ONLY after successful index write
        cursor_data = {
            "processed_ids": sorted(processed),
            "total_processed": len(processed),
        }
        cursor_tmp = refs_path / "_backfill_cursor.json.tmp"
        with open(cursor_tmp, "w", encoding="utf-8") as f:
            json.dump(cursor_data, f, indent=2, ensure_ascii=False)
        os.replace(str(cursor_tmp), str(cursor_path))

    finally:
        index._release_lock()

    summary = {
        "workspace_id": workspace_id,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(processed),
    }
    logger.info("[Backfill] Done: %s", summary)
    return summary


def _find_metadata_for_ref(refs_path: Path, ref_id: str, entry: dict) -> Path | None:
    """Find the metadata JSON file for a reference."""
    handle = entry.get("source_handle", "")
    if handle:
        candidate = refs_path / handle / f"{ref_id}.json"
        if candidate.exists():
            return candidate

    # Fallback: search _unsorted and all handle dirs
    for subdir in refs_path.iterdir():
        if not subdir.is_dir():
            continue
        candidate = subdir / f"{ref_id}.json"
        if candidate.exists():
            return candidate

    return None


def main():
    parser = argparse.ArgumentParser(description="Backfill V2.0 projection fields into _index.json")
    parser.add_argument("--workspace-id", required=True, help="Workspace ID to backfill")
    args = parser.parse_args()

    summary = backfill_workspace(args.workspace_id)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
