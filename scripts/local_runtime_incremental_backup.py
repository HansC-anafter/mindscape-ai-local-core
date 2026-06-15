#!/usr/bin/env python3
"""Compatibility facade for incremental local runtime backup policy and execution."""

from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from local_runtime_incremental_backup_lib import config as _config
from local_runtime_incremental_backup_lib import filesystem as _filesystem
from local_runtime_incremental_backup_lib import mirror as _mirror
from local_runtime_incremental_backup_lib import planner as _planner
from local_runtime_incremental_backup_lib import policy as _policy
from local_runtime_incremental_backup_lib import postgres as _postgres
from local_runtime_incremental_backup_lib import snapshot as _snapshot
from local_runtime_incremental_backup_lib import verify as _verify

MODE = _config.MODE
REPO_ROOT = _config.REPO_ROOT
VERIFY_SCRIPT = _config.VERIFY_SCRIPT
BYTES_PER_GB = _config.BYTES_PER_GB
WAL_ARCHIVE_CONTAINER_DIR = _config.WAL_ARCHIVE_CONTAINER_DIR
WAL_SEGMENT_BYTES = _config.WAL_SEGMENT_BYTES
WAL_SEGMENT_RE = _config.WAL_SEGMENT_RE
BACKUP_LABEL_START_WAL_RE = _config.BACKUP_LABEL_START_WAL_RE
MANAGED_ARCHIVE_COMMAND = _config.MANAGED_ARCHIVE_COMMAND
TRANSIENT_RSYNC_CODES = _config.TRANSIENT_RSYNC_CODES
RSYNC_SNAPSHOT_EXCLUDES = _config.RSYNC_SNAPSHOT_EXCLUDES
MIRROR_SCOPE_POSTGRES = _config.MIRROR_SCOPE_POSTGRES
MIRROR_DEFAULT_SCOPES = _config.MIRROR_DEFAULT_SCOPES
MIRROR_SCOPE_DEFINITIONS = _config.MIRROR_SCOPE_DEFINITIONS

load_repo_env = _config.load_repo_env
utc_now = _config.utc_now
utc_stamp = _config.utc_stamp
parse_bool = _config.parse_bool
parse_int = _config.parse_int
parse_float = _config.parse_float
parse_datetime = _config.parse_datetime
archiver_currently_failing = _config.archiver_currently_failing
parse_scopes = _config.parse_scopes

run_text = _filesystem.run_text
run_capture = _filesystem.run_capture
read_json = _filesystem.read_json
write_json = _filesystem.write_json
resolve_path = _filesystem.resolve_path
resolve_data_host_dir = _filesystem.resolve_data_host_dir
resolve_primary_root = _filesystem.resolve_primary_root
resolve_mirror_root = _filesystem.resolve_mirror_root
resolve_wal_archive_root = _filesystem.resolve_wal_archive_root
disk_free_bytes = _filesystem.disk_free_bytes
path_contains = _filesystem.path_contains
state_root = _filesystem.state_root
base_root = _filesystem.base_root
metadata_root = _filesystem.metadata_root
latest_pointer = _filesystem.latest_pointer
base_manifest_path = _filesystem.base_manifest_path
list_wal_segments = _filesystem.list_wal_segments
wal_archive_segment_size_mismatches = _filesystem.wal_archive_segment_size_mismatches
base_backup_start_segment = _filesystem.base_backup_start_segment
dir_size_bytes = _filesystem.dir_size_bytes
parse_du_output_bytes = _filesystem.parse_du_output_bytes
disk_usage_many_bytes = _filesystem.disk_usage_many_bytes
disk_usage_bytes = _filesystem.disk_usage_bytes
mixed_path_usage_bytes = _filesystem.mixed_path_usage_bytes
rsync_snapshot_base_cmd = _filesystem.rsync_snapshot_base_cmd
snapshot_path_excluded = _filesystem.snapshot_path_excluded
mirror_scope_entries = _filesystem.mirror_scope_entries
add_include_ancestors = _filesystem.add_include_ancestors
add_mirror_scope_filters = _filesystem.add_mirror_scope_filters
parse_rsync_stat_bytes = _filesystem.parse_rsync_stat_bytes
snapshot_source_size_bytes = _filesystem.snapshot_source_size_bytes
scoped_source_size_bytes = _filesystem.scoped_source_size_bytes
estimate_bytes_from_rsync_result = _filesystem.estimate_bytes_from_rsync_result
use_rsync_dry_run_estimate = _filesystem.use_rsync_dry_run_estimate
estimate_temp_parent = _filesystem.estimate_temp_parent
latest_incremental_manifest = _filesystem.latest_incremental_manifest
latest_base = _filesystem.latest_base
age_hours = _filesystem.age_hours
command_exists = _filesystem.command_exists

safe_name = _planner.safe_name
rsync_snapshot_command = _snapshot.rsync_snapshot_command
run_rsync_snapshot_attempts = _snapshot.run_rsync_snapshot_attempts
manifest_created_at = _snapshot.manifest_created_at
incremental_manifests = _snapshot.incremental_manifests
wal_manifest_entry_required = _snapshot.wal_manifest_entry_required
refresh_manifest_wal_state = _snapshot.refresh_manifest_wal_state
clone_json = _verify.clone_json
mirror_manifest_for_root = _mirror.mirror_manifest_for_root
build_previous_snapshot = _policy.build_previous_snapshot
previous_mirror_snapshot = _policy.previous_mirror_snapshot

_PLAIN_SYNC_NAMES = (
    "run_text",
    "run_capture",
    "disk_free_bytes",
    "disk_usage_many_bytes",
    "disk_usage_bytes",
    "dir_size_bytes",
    "command_exists",
    "resolve_data_host_dir",
)
_SYNC_MODULES = (_filesystem, _postgres, _planner, _snapshot, _verify, _mirror, _policy)
_FACADE_WRAPPERS = {}


def _sync_dependency_overrides() -> None:
    for module in _SYNC_MODULES:
        for name in _PLAIN_SYNC_NAMES:
            if hasattr(module, name):
                setattr(module, name, globals()[name])
    _planner.postgres_status = (
        _postgres.postgres_status
        if globals()["postgres_status"] is _FACADE_WRAPPERS.get("postgres_status")
        else globals()["postgres_status"]
    )
    _policy.estimate_snapshot_transfer_bytes = (
        _filesystem.estimate_snapshot_transfer_bytes
        if globals()["estimate_snapshot_transfer_bytes"]
        is _FACADE_WRAPPERS.get("estimate_snapshot_transfer_bytes")
        else globals()["estimate_snapshot_transfer_bytes"]
    )
    _policy.estimate_mirror_snapshot_transfer_bytes = (
        _filesystem.estimate_mirror_snapshot_transfer_bytes
        if globals()["estimate_mirror_snapshot_transfer_bytes"]
        is _FACADE_WRAPPERS.get("estimate_mirror_snapshot_transfer_bytes")
        else globals()["estimate_mirror_snapshot_transfer_bytes"]
    )


def estimate_snapshot_transfer_bytes(source, previous, timeout_seconds):
    _sync_dependency_overrides()
    return _filesystem.estimate_snapshot_transfer_bytes(source, previous, timeout_seconds)


def estimate_mirror_snapshot_transfer_bytes(source, previous, scopes, timeout_seconds):
    _sync_dependency_overrides()
    return _filesystem.estimate_mirror_snapshot_transfer_bytes(source, previous, scopes, timeout_seconds)


def postgres_status():
    _sync_dependency_overrides()
    return _postgres.postgres_status()


def build_config(args):
    _sync_dependency_overrides()
    return _planner.build_config(args)


def build_plan(args):
    _sync_dependency_overrides()
    return _planner.build_plan(args)


def run_pg_basebackup(base_id, wal_root, timeout_seconds):
    _sync_dependency_overrides()
    return _postgres.run_pg_basebackup(base_id, wal_root, timeout_seconds)


def switch_wal() -> None:
    _sync_dependency_overrides()
    return _postgres.switch_wal()


def rsync_snapshot(source, target, previous, timeout_seconds):
    _sync_dependency_overrides()
    return _snapshot.rsync_snapshot(source, target, previous, timeout_seconds)


def prune_incremental(primary_root, keep_count, protected, *, wal_root=None):
    _sync_dependency_overrides()
    return _snapshot.prune_incremental(primary_root, keep_count, protected, wal_root=wal_root)


def verify_incremental_dir(backup_dir, *, restore_drill=False):
    _sync_dependency_overrides()
    return _verify.verify_incremental_dir(backup_dir, restore_drill=restore_drill)


def mirror_incremental_artifacts(
    *,
    primary_root,
    mirror_root,
    backup_dir,
    wal_root,
    manifest,
    timeout_seconds,
    retention_count,
    mirror_scopes,
):
    _sync_dependency_overrides()
    return _mirror.mirror_incremental_artifacts(
        primary_root=primary_root,
        mirror_root=mirror_root,
        backup_dir=backup_dir,
        wal_root=wal_root,
        manifest=manifest,
        timeout_seconds=timeout_seconds,
        retention_count=retention_count,
        mirror_scopes=mirror_scopes,
    )


def capacity_preflight(*, plan, config, previous_manifest, previous_snapshot, timeout_seconds):
    _sync_dependency_overrides()
    return _policy.capacity_preflight(
        plan=plan,
        config=config,
        previous_manifest=previous_manifest,
        previous_snapshot=previous_snapshot,
        timeout_seconds=timeout_seconds,
    )


def run_policy(args):
    _sync_dependency_overrides()
    return _policy.run_policy(args)


_FACADE_WRAPPERS.update(
    {
        "estimate_snapshot_transfer_bytes": estimate_snapshot_transfer_bytes,
        "estimate_mirror_snapshot_transfer_bytes": estimate_mirror_snapshot_transfer_bytes,
        "postgres_status": postgres_status,
    }
)
