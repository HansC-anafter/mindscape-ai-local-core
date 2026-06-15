"""Models and constants for local runtime backup system-settings routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


BACKUP_CATEGORY = "backup"
KEY_BACKUP_ROOT = "local_runtime_backup.backup_root"
KEY_MIRROR_ROOT = "local_runtime_backup.mirror_root"
KEY_RETENTION_LOCAL_COUNT = "local_runtime_backup.retention_local_count"
KEY_RETENTION_MIRROR_COUNT = "local_runtime_backup.retention_mirror_count"
KEY_MIN_FREE_GB = "local_runtime_backup.min_free_gb"
KEY_REQUIRE_MIRROR = "local_runtime_backup.require_mirror"
KEY_BASE_INTERVAL_HOURS = "local_runtime_backup.base_interval_hours"
KEY_MIRROR_SCOPES = "local_runtime_backup.mirror_scopes"
KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED = "local_runtime_backup.google_drive_resource_sync_enabled"
KEY_GOOGLE_DRIVE_RESOURCE_ROOT = "local_runtime_backup.google_drive_resource_root"

DEFAULT_MIRROR_SCOPES = ["postgres_chain", "runtime_metadata", "auth_state"]
AVAILABLE_MIRROR_SCOPES = {
    "postgres_chain",
    "runtime_metadata",
    "auth_state",
    "blob_storage",
    "model_cache",
    "workspace_artifacts",
}

LOCALHOST_ADDRS = {"127.0.0.1", "localhost", "::1", "unknown", "testclient"}
DOCKER_LOCAL_PREFIXES = ("172.", "192.168.65.")



class LocalRuntimeBackupConfig(BaseModel):
    backup_root: str = ""
    mirror_root: str = ""
    retention_local_count: int = 7
    retention_mirror_count: int = 3
    min_free_gb: float = 20.0
    require_mirror: bool = False
    base_interval_hours: int = 168
    mirror_scopes: List[str] = Field(default_factory=lambda: list(DEFAULT_MIRROR_SCOPES))
    google_drive_resource_sync_enabled: bool = False
    google_drive_resource_root: str = ""


class GoogleDriveRuntimeSyncStatus(BaseModel):
    available: bool = False
    account_label: str = ""
    mount_path: str = ""
    my_drive_path: str = ""
    recommended_mirror_root: str = ""
    recommended_resource_root: str = ""
    recommended_mirror_scopes: List[str] = Field(default_factory=lambda: list(DEFAULT_MIRROR_SCOPES))
    mirror_root_active: bool = False
    resource_sync_enabled: bool = False
    resource_root: str = ""
    warnings: List[str] = Field(default_factory=list)


class LocalRuntimeBackupStatus(BaseModel):
    config: LocalRuntimeBackupConfig
    backup_root: str
    policy: Dict[str, Any] = Field(default_factory=dict)
    primary_free_bytes: Optional[int] = None
    mirror_free_bytes: Optional[int] = None
    postgres_archive_mode: Optional[str] = None
    postgres_wal_ready_count: Optional[int] = None
    postgres_wal_bytes: Optional[int] = None
    wal_archive_dir: Optional[str] = None
    wal_segment_count: Optional[int] = None
    wal_archive_bytes: Optional[int] = None
    base_backup_id: Optional[str] = None
    base_backup_created_at: Optional[str] = None
    base_backup_age_hours: Optional[float] = None
    base_backup_required: Optional[bool] = None
    latest_file_snapshot_id: Optional[str] = None
    can_run: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)
    script_available: bool
    verify_script_available: bool
    host_project_root: str
    device_node_available: bool
    latest_backup: Optional[Dict[str, Any]] = None
    latest_job: Optional[Dict[str, Any]] = None
    commands: Dict[str, str]
    google_drive_sync: GoogleDriveRuntimeSyncStatus = Field(default_factory=GoogleDriveRuntimeSyncStatus)
    warnings: List[str] = Field(default_factory=list)


class BackupJobRequest(BaseModel):
    backup_root: Optional[str] = None
    mirror_root: Optional[str] = None
    retention_local_count: Optional[int] = None
    retention_mirror_count: Optional[int] = None
    min_free_gb: Optional[float] = None
    require_mirror: Optional[bool] = None
    base_interval_hours: Optional[int] = None
    mirror_scopes: Optional[List[str]] = None


class VerifyBackupRequest(BaseModel):
    backup_dir: Optional[str] = None


class GoogleDrivePrepareRequest(BaseModel):
    mirror_root: Optional[str] = None
    resource_root: Optional[str] = None
