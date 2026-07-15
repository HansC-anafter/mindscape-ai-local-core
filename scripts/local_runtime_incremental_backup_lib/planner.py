#!/usr/bin/env python3
"""Policy planning helpers for incremental backups."""

from __future__ import annotations

import argparse
import os
from typing import Any

from .config import (
    BYTES_PER_GB,
    MANAGED_ARCHIVE_COMMAND,
    MIRROR_SCOPE_DEFINITIONS,
    MODE,
    archiver_currently_failing,
    parse_bool,
    parse_float,
    parse_int,
    parse_scopes,
)
from .filesystem import (
    command_exists,
    disk_free_bytes,
    disk_usage_bytes,
    list_wal_segments,
    path_contains,
    resolve_data_host_dir,
    resolve_mirror_root,
    resolve_primary_root,
    resolve_wal_archive_root,
    wal_archive_segment_size_mismatches,
)
from .postgres import postgres_status
from .runtime_admission import inspect_backup_runtime_admission
from .snapshot_index import age_hours, latest_base, latest_runtime_snapshot


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    primary_root = resolve_primary_root(getattr(args, "output_dir", None))
    mirror_root = resolve_mirror_root(getattr(args, "mirror_root", None))
    min_free_gb = parse_float(
        getattr(args, "min_free_gb", None) or os.environ.get("LOCAL_CORE_BACKUP_MIN_FREE_GB"),
        20.0,
    )
    require_mirror = parse_bool(
        getattr(args, "require_mirror", None),
        parse_bool(os.environ.get("LOCAL_CORE_BACKUP_REQUIRE_MIRROR"), False),
    )
    local_retention = parse_int(
        getattr(args, "retention_local_count", None)
        or os.environ.get("LOCAL_CORE_BACKUP_RETENTION_LOCAL_COUNT"),
        default=7,
        minimum=1,
    )
    mirror_retention = parse_int(
        getattr(args, "retention_mirror_count", None)
        or os.environ.get("LOCAL_CORE_BACKUP_RETENTION_MIRROR_COUNT"),
        default=3,
        minimum=1,
    )
    base_interval_hours = parse_int(
        getattr(args, "base_interval_hours", None)
        or os.environ.get("LOCAL_CORE_BACKUP_BASE_INTERVAL_HOURS"),
        default=168,
        minimum=1,
    )
    mirror_scopes = parse_scopes(
        getattr(args, "mirror_scopes", None) or os.environ.get("LOCAL_CORE_BACKUP_MIRROR_SCOPES")
    )
    postgres_only = bool(getattr(args, "postgres_only", False))
    return {
        "primary_root": primary_root,
        "mirror_root": mirror_root,
        "min_free_gb": min_free_gb,
        "require_mirror": require_mirror,
        "retention_local_count": local_retention,
        "retention_mirror_count": mirror_retention,
        "base_interval_hours": base_interval_hours,
        "mirror_scopes": mirror_scopes,
        "postgres_only": postgres_only,
        "wal_archive_root": resolve_wal_archive_root(primary_root),
    }


def _policy_payload(config: dict[str, Any]) -> dict[str, Any]:
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    return {
        "mode": MODE,
        "primary_root": str(primary_root),
        "mirror_root": str(mirror_root) if mirror_root else "",
        "retention_local_count": config["retention_local_count"],
        "retention_mirror_count": config["retention_mirror_count"],
        "min_free_gb": config["min_free_gb"],
        "require_mirror": config["require_mirror"],
        "base_interval_hours": config["base_interval_hours"],
        "mirror_scopes": config["mirror_scopes"],
        "backup_scope": (
            "postgres_chain_only" if config["postgres_only"] else "runtime_snapshot_and_postgres_chain"
        ),
        "mirror_scope_definitions": MIRROR_SCOPE_DEFINITIONS,
        "wal_archive_root": str(config["wal_archive_root"]),
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    config = build_config(args)
    policy = _policy_payload(config)
    runtime_data_root = resolve_data_host_dir()
    storage_topology = {
        "runtime_data_root": str(runtime_data_root),
        "backup_root": str(config["primary_root"]),
        "isolated_from_runtime_bind": not path_contains(
            runtime_data_root,
            config["primary_root"],
        ),
    }
    if not storage_topology["isolated_from_runtime_bind"]:
        return {
            "policy": policy,
            "preflight_status": "topology_blocked",
            "storage_topology": storage_topology,
            "can_run": False,
            "blocking_reasons": ["backup_root_inside_runtime_bind_mount"],
            "warnings": [],
        }
    runtime_admission = inspect_backup_runtime_admission(
        wal_archive_root=config["wal_archive_root"]
    )
    if not runtime_admission["admitted"]:
        return {
            "policy": policy,
            "preflight_status": "runtime_deferred",
            "storage_topology": storage_topology,
            "runtime_admission": runtime_admission,
            "can_run": False,
            "blocking_reasons": list(runtime_admission["blocking_reasons"]),
            "warnings": [],
        }
    primary_root = config["primary_root"]
    mirror_root = config["mirror_root"]
    wal_root = config["wal_archive_root"]
    min_free_bytes = int(config["min_free_gb"] * BYTES_PER_GB)
    warnings: list[str] = []
    blocking_reasons: list[str] = []

    primary_free = disk_free_bytes(primary_root)
    mirror_free = disk_free_bytes(mirror_root) if mirror_root else None
    if primary_free < min_free_bytes:
        blocking_reasons.append("primary_backup_root_below_min_free_space")
    if config["require_mirror"] and mirror_root is None:
        blocking_reasons.append("mirror_required_but_not_configured")
    if mirror_root and mirror_free is not None and mirror_free < min_free_bytes:
        blocking_reasons.append("mirror_backup_root_below_min_free_space")
    if config["retention_mirror_count"] > config["retention_local_count"]:
        blocking_reasons.append("mirror_retention_exceeds_local_retention")
    if config["postgres_only"] and (mirror_root is not None or config["require_mirror"]):
        blocking_reasons.append("postgres_only_requires_local_only")
    if not config["postgres_only"] and not command_exists("rsync"):
        blocking_reasons.append("rsync_not_available")

    if not path_contains(primary_root, wal_root):
        blocking_reasons.append("wal_archive_outside_backup_root")

    pg = postgres_status()
    archive_mode = str(pg.get("archive_mode") or "unknown")
    archive_command = str(pg.get("archive_command") or "")
    if archive_mode != "on":
        blocking_reasons.append("postgres_archive_required")
    if MANAGED_ARCHIVE_COMMAND not in archive_command:
        blocking_reasons.append("postgres_archive_command_not_managed")
    if archiver_currently_failing(pg):
        blocking_reasons.append("postgres_archiver_currently_failing")
    elif parse_int(pg.get("archiver_failed_count"), 0) > 0:
        warnings.append("postgres_archiver_historical_failures_present")
    if pg.get("error"):
        warnings.append(str(pg["error"]))

    latest_base_manifest = latest_base(primary_root)
    latest_snapshot, _latest_snapshot_path = latest_runtime_snapshot(primary_root)
    base_age = age_hours(str(latest_base_manifest.get("created_at"))) if latest_base_manifest else None
    base_required = latest_base_manifest is None or (
        base_age is not None and base_age >= config["base_interval_hours"]
    )
    wal_segments = list_wal_segments(wal_root)
    wal_size_mismatches = wal_archive_segment_size_mismatches(wal_root)
    if wal_size_mismatches:
        blocking_reasons.append("wal_archive_segment_size_mismatch")
        sample = ",".join(str(item["name"]) for item in wal_size_mismatches[:10])
        warnings.append(f"wal_archive_segment_size_mismatch:{sample}")

    return {
        "policy": policy,
        "preflight_status": "completed",
        "primary_free_bytes": primary_free,
        "mirror_free_bytes": mirror_free,
        "min_free_bytes": min_free_bytes,
        "postgres_archive_mode": archive_mode,
        "postgres_archive_command": archive_command,
        "postgres_wal_ready_count": pg.get("wal_ready_count", 0),
        "postgres_wal_bytes": pg.get("wal_bytes", 0),
        "postgres_archiver_archived_count": pg.get("archiver_archived_count", 0),
        "postgres_archiver_last_archived_wal": pg.get("archiver_last_archived_wal", ""),
        "postgres_archiver_last_archived_time": pg.get("archiver_last_archived_time", ""),
        "postgres_archiver_failed_count": pg.get("archiver_failed_count", 0),
        "postgres_archiver_last_failed_wal": pg.get("archiver_last_failed_wal", ""),
        "postgres_archiver_last_failed_time": pg.get("archiver_last_failed_time", ""),
        "postgres_archiver_stats_reset": pg.get("archiver_stats_reset", ""),
        "wal_archive_dir": str(wal_root),
        "wal_segment_count": len(wal_segments),
        "wal_segment_size_mismatches": wal_size_mismatches,
        "wal_archive_bytes": disk_usage_bytes(wal_root),
        "base_backup_id": latest_base_manifest.get("base_backup_id") if latest_base_manifest else "",
        "base_backup_created_at": latest_base_manifest.get("created_at") if latest_base_manifest else "",
        "base_backup_age_hours": base_age,
        "base_backup_required": base_required,
        "latest_file_snapshot_id": latest_snapshot.get("backup_name") if latest_snapshot else "",
        "storage_topology": storage_topology,
        "runtime_admission": runtime_admission,
        "can_run": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
    }


def safe_name(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    return "".join(ch if ch in allowed else "_" for ch in value)
