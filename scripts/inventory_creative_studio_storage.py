from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


COLLECTIONS = (
    "source_refs",
    "board_items",
    "tool_runs",
    "variants",
    "handoffs",
    "snapshots",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


root = Path(os.environ["LOCAL_STORAGE_PATH"]).resolve()
records: list[dict[str, object]] = []
errors: list[dict[str, str]] = []
for path in sorted(root.glob("*/creative_studio/spaces/*.json")):
    relative_path = path.relative_to(root).as_posix()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("bundle_not_object")
        space = payload.get("space")
        if not isinstance(space, dict):
            raise ValueError("space_not_object")
        counts = {
            name: len(payload.get(name)) if isinstance(payload.get(name), list) else 0
            for name in COLLECTIONS
        }
        records.append(
            {
                "relative_path": relative_path,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "tenant_id": path.parents[2].name,
                "space_id": str(space.get("space_id") or ""),
                "workspace_id": str(space.get("workspace_id") or ""),
                "counts": counts,
            }
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(
            {
                "relative_path": relative_path,
                "error": f"{type(exc).__name__}:{exc}",
            }
        )

canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
totals = {name: sum(int(record["counts"][name]) for record in records) for name in COLLECTIONS}
print(
    json.dumps(
        {
            "schema_version": "creative-studio-file-inventory.v1",
            "storage_root": str(root),
            "bundle_count": len(records),
            "total_bytes": sum(int(record["bytes"]) for record in records),
            "collection_totals": totals,
            "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
            "records": records,
            "errors": errors,
        },
        indent=2,
        sort_keys=True,
    )
)
