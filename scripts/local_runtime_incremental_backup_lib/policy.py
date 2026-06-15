#!/usr/bin/env python3
"""Run-policy orchestration for incremental backups."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from .config import BYTES_PER_GB, MIRROR_SCOPE_DEFINITIONS, MODE, parse_int, utc_now, utc_stamp
from .filesystem import (
    dir_size_bytes,
    disk_free_bytes,
    disk_usage_bytes,
    estimate_mirror_snapshot_transfer_bytes,
    estimate_snapshot_transfer_bytes,
    latest_incremental_manifest,
    latest_base,
    latest_pointer,
    list_wal_segments,
    resolve_data_host_dir,
    write_json,
)
from .mirror import mirror_incremental_artifacts
from .planner import build_config, build_plan, safe_name
from .postgres import run_pg_basebackup, switch_wal
from .snapshot import prune_incremental, refresh_manifest_wal_state, rsync_snapshot
from .verify import verify_incremental_dir


def build_previous_snapshot(primary_root: Path) -> tuple[dict[str, Any] | None, Path | None]:
    previous_manifest = latest_incremental_manifest(primary_root)
    if not previous_manifest:
        return None, None
    previous_backup_dir = Path(str(previous_manifest.get("backup_dir") or ""))
    previous_rel = str(previous_manifest.get("components", {}).get("files", {}).get("snapshot_relpath") or "app-data")
    return previous_manifest, previous_backup_dir / previous_rel


def previous_mirror_snapshot(mirror_root: Path | None, previous_manifest: dict[str, Any] | None) -> Path | None:
    if not mirror_root or not previous_manifest:
        return None
    previous_snapshot_id = str(previous_manifest.get("backup_name") or "")
    if not previous_snapshot_id:
        return None
    candidate = mirror_root / previous_snapshot_id / "app-data"
    return candidate if candidate.is_dir() else None


def capacity_preflight(
    *,
    plan: dict[str, Any],
    config: dict[str, Any],
    previous_manifest: dict[str, Any] | None,
    previous_snapshot: Path | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    wal_root = config["wal_archive_root"]
    min_free_bytes = int(config["min_free_gb"] * BYTES_PER_GB)
    snapshot_transfer_bytes = estimate_snapshot_transfer_bytes(
        resolve_data_host_dir(),
        previous_snapshot,
        timeout_seconds,
    )
    mirror_snapshot_transfer_bytes = 0
    if mirror_root:
        mirror_snapshot_transfer_bytes = estimate_mirror_snapshot_transfer_bytes(
            resolve_data_host_dir(),
            previous_mirror_snapshot(mirror_root, previous_manifest),
            config["mirror_scopes"],
            timeout_seconds,
        )
    postgres_base_estimate_bytes = (
        disk_usage_bytes(resolve_data_host_dir() / "postgres") if plan["base_backup_required"] else 0
    )
    wal_estimate_bytes = parse_int(plan.get("wal_archive_bytes"), 0)
    if wal_estimate_bytes <= 0:
        wal_estimate_bytes = disk_usage_bytes(wal_root)
    primary_estimated_required_bytes = snapshot_transfer_bytes + postgres_base_estimate_bytes
    mirror_estimated_required_bytes = mirror_snapshot_transfer_bytes + postgres_base_estimate_bytes + wal_estimate_bytes
    primary_free = disk_free_bytes(primary_root)
    mirror_free = disk_free_bytes(mirror_root) if mirror_root else None

    blocking_reasons = []
    if primary_free < primary_estimated_required_bytes + min_free_bytes:
        blocking_reasons.append("primary_backup_root_below_estimated_required_space")
    if mirror_root and mirror_free is not None and mirror_free < mirror_estimated_required_bytes + min_free_bytes:
        blocking_reasons.append("mirror_backup_root_below_estimated_required_space")
    return {
        "snapshot_transfer_bytes": snapshot_transfer_bytes,
        "mirror_snapshot_transfer_bytes": mirror_snapshot_transfer_bytes,
        "postgres_base_estimate_bytes": postgres_base_estimate_bytes,
        "wal_estimate_bytes": wal_estimate_bytes,
        "estimated_required_bytes": primary_estimated_required_bytes,
        "primary_estimated_required_bytes": primary_estimated_required_bytes,
        "mirror_estimated_required_bytes": mirror_estimated_required_bytes,
        "min_free_bytes": min_free_bytes,
        "primary_free_bytes": primary_free,
        "mirror_free_bytes": mirror_free,
        "mirror_scopes": config["mirror_scopes"],
        "blocking_reasons": blocking_reasons,
    }


def run_policy(args: argparse.Namespace) -> dict[str, Any]:
    plan = build_plan(args)
    if not plan["can_run"]:
        raise SystemExit("Backup policy preflight failed: " + ", ".join(plan["blocking_reasons"]))

    config = build_config(args)
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    wal_root = config["wal_archive_root"]
    timeout_seconds = int(getattr(args, "timeout_seconds", 7200) or 7200)
    backup_name = safe_name(getattr(args, "name", None) or f"mindscape_local_runtime_{utc_stamp()}")
    backup_dir = primary_root / backup_name
    partial_dir = primary_root / f".{backup_name}.partial"
    if backup_dir.exists():
        raise SystemExit(f"Backup already exists: {backup_dir}")
    if partial_dir.exists():
        shutil.rmtree(partial_dir)

    previous_manifest, previous_snapshot = build_previous_snapshot(primary_root)
    capacity = capacity_preflight(
        plan=plan,
        config=config,
        previous_manifest=previous_manifest,
        previous_snapshot=previous_snapshot,
        timeout_seconds=timeout_seconds,
    )
    if capacity["blocking_reasons"]:
        raise SystemExit("Backup capacity preflight failed: " + ", ".join(capacity["blocking_reasons"]))

    partial_dir.mkdir(parents=True, exist_ok=True)

    before_wal = list_wal_segments(wal_root)
    active_base = latest_base(primary_root)
    if plan["base_backup_required"]:
        base_id = f"base_{utc_stamp()}"
        active_base = run_pg_basebackup(base_id, wal_root, timeout_seconds)
    if not active_base:
        raise SystemExit("No verified base backup is available")

    switch_wal()
    after_wal = list_wal_segments(wal_root)
    new_wal = [name for name in after_wal if name not in before_wal]

    snapshot_dir = partial_dir / "app-data"
    rsync_results = rsync_snapshot(resolve_data_host_dir(), snapshot_dir, previous_snapshot, timeout_seconds)

    created_at = utc_now()
    base_dir = Path(str(active_base["host_base_dir"]))
    manifest = {
        "schema_version": "2.0",
        "mode": MODE,
        "backup_name": backup_name,
        "created_at": created_at,
        "backup_dir": str(backup_dir),
        "components": {
            "postgres": {
                "base_backup_id": active_base["base_backup_id"],
                "base_backup_dir": str(base_dir),
                "container_base_dir": active_base.get("container_base_dir"),
                "base_backup_created_at": active_base.get("created_at"),
                "base_backup_start_wal_segment": active_base.get("start_wal_segment", ""),
                "base_backup_required": plan["base_backup_required"],
                "wal_archive_dir": str(wal_root),
                "wal_start_segment": new_wal[0] if new_wal else (after_wal[0] if after_wal else ""),
                "wal_end_segment": new_wal[-1] if new_wal else (after_wal[-1] if after_wal else ""),
                "wal_segments": after_wal,
                "new_wal_segments": new_wal,
                "wal_segment_count": len(after_wal),
                "wal_archive_bytes": dir_size_bytes(wal_root),
                "archive_mode": plan["postgres_archive_mode"],
            },
            "files": {
                "snapshot_relpath": "app-data",
                "previous_snapshot_id": previous_manifest.get("backup_name") if previous_manifest else "",
                "source_host_dir": str(resolve_data_host_dir()),
                "bytes": dir_size_bytes(snapshot_dir),
                "estimated_transfer_bytes": capacity["snapshot_transfer_bytes"],
                "rsync_results": rsync_results,
            },
        },
        "total_bytes": dir_size_bytes(snapshot_dir) + dir_size_bytes(base_dir),
        "capacity_preflight": capacity,
        "mirror": {
            "scope_mode": "selected_data_scopes",
            "scopes": config["mirror_scopes"],
            "scope_definitions": MIRROR_SCOPE_DEFINITIONS,
        },
        "verification": {"primary": "pending", "mirror": "pending"},
    }
    write_json(partial_dir / "manifest.json", manifest)
    partial_dir.rename(backup_dir)
    manifest["backup_dir"] = str(backup_dir)
    write_json(backup_dir / "manifest.json", manifest)

    primary_verify = verify_incremental_dir(backup_dir)
    manifest["verification"]["primary"] = "passed"
    write_json(backup_dir / "manifest.json", manifest)
    write_json(
        latest_pointer(primary_root),
        {
            "latest_backup_name": backup_name,
            "latest_backup_dir": str(backup_dir),
            "updated_at": utc_now(),
        },
    )

    local_pruned = prune_incremental(primary_root, config["retention_local_count"], backup_dir, wal_root=wal_root)
    refresh_manifest_wal_state(manifest, wal_root)
    write_json(backup_dir / "manifest.json", manifest)
    mirror_result: dict[str, Any] = {"enabled": False}
    if mirror_root is not None:
        mirror_result = mirror_incremental_artifacts(
            primary_root=primary_root,
            mirror_root=mirror_root,
            backup_dir=backup_dir,
            wal_root=wal_root,
            manifest=manifest,
            timeout_seconds=timeout_seconds,
            retention_count=config["retention_mirror_count"],
            mirror_scopes=config["mirror_scopes"],
        )
        manifest["verification"]["mirror"] = "passed"
        write_json(backup_dir / "manifest.json", manifest)

    return {
        "success": True,
        "created_at": created_at,
        "backup_name": backup_name,
        "backup_dir": str(backup_dir),
        "mirror_dir": mirror_result.get("mirror_dir", ""),
        "policy": plan["policy"],
        "manifest": manifest,
        "verify": primary_verify,
        "mirror": mirror_result,
        "pruned": {"local": local_pruned, "mirror": mirror_result.get("pruned", [])},
    }
