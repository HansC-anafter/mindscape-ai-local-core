#!/usr/bin/env python3
"""Audit installed packs against runtime/source locations.

Usage:
  PYTHONPATH=/app/backend python backend/scripts/audit_pack_runtime_alignment.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text

from app.services.stores.installed_packs_store import InstalledPacksStore
from app.services.stores.pack_activation_state_store import PackActivationStateStore


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES_ROOT = BACKEND_ROOT / "app" / "capabilities"
FEATURES_ROOT = BACKEND_ROOT / "features"


def _collect_runtime_locations(pack_id: str) -> Dict[str, Any]:
    capability_dir = CAPABILITIES_ROOT / pack_id
    feature_dir = FEATURES_ROOT / pack_id
    capability_manifest = capability_dir / "manifest.yaml"

    locations: List[str] = []
    runtime_kind = "runtime_missing"

    if capability_manifest.exists():
        runtime_kind = "capability_manifest"
        locations.append(str(capability_manifest.relative_to(BACKEND_ROOT)))
    elif feature_dir.exists():
        runtime_kind = "feature_pack"
        locations.append(str(feature_dir.relative_to(BACKEND_ROOT)))
    elif capability_dir.exists():
        runtime_kind = "capability_dir_without_manifest"
        locations.append(str(capability_dir.relative_to(BACKEND_ROOT)))

    if feature_dir.exists() and str(feature_dir.relative_to(BACKEND_ROOT)) not in locations:
        locations.append(str(feature_dir.relative_to(BACKEND_ROOT)))

    return {
        "runtime_kind": runtime_kind,
        "locations": locations,
    }


def _is_source_only_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    try:
        path = Path(file_path)
    except Exception:
        return False
    return "mindscape-ai-cloud" in str(path)


def main() -> int:
    installed_store = InstalledPacksStore()
    activation_store = PackActivationStateStore()

    installed_rows = {row["pack_id"]: row for row in installed_store.list_installed_metadata()}

    with activation_store.get_connection() as conn:
        activation_rows = conn.execute(
            text(
                """
                SELECT pack_id, pack_family, activation_state, embedding_state,
                       manifest_hash, registered_prefixes, last_error
                FROM pack_activation_state
                ORDER BY pack_id
                """
            )
        ).fetchall()

    report: List[Dict[str, Any]] = []
    for row in activation_rows:
        installed = installed_rows.get(row.pack_id)
        metadata = installed.get("metadata", {}) if installed else {}
        runtime = _collect_runtime_locations(row.pack_id)
        file_path = metadata.get("_file_path")

        report.append(
            {
                "pack_id": row.pack_id,
                "enabled": bool(installed.get("enabled")) if installed else False,
                "pack_family": row.pack_family,
                "activation_state": row.activation_state,
                "embedding_state": row.embedding_state,
                "runtime_kind": runtime["runtime_kind"],
                "locations": runtime["locations"],
                "metadata_file_path": file_path,
                "source_only_metadata_path": _is_source_only_path(file_path),
                "registered_prefixes": json.loads(row.registered_prefixes or "[]")
                if isinstance(row.registered_prefixes, str)
                else (row.registered_prefixes or []),
                "last_error": row.last_error,
            }
        )

    summary = {
        "total": len(report),
        "runtime_missing": sum(1 for item in report if item["runtime_kind"] == "runtime_missing"),
        "feature_pack": sum(1 for item in report if item["runtime_kind"] == "feature_pack"),
        "capability_manifest": sum(1 for item in report if item["runtime_kind"] == "capability_manifest"),
        "source_only_metadata_path": sum(1 for item in report if item["source_only_metadata_path"]),
    }

    print("# Pack Runtime Alignment Audit")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()
    for item in report:
        if item["runtime_kind"] == "capability_manifest" and not item["source_only_metadata_path"]:
            continue
        print(json.dumps(item, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
