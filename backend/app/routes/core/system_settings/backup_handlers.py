"""FastAPI route handlers for local runtime backup settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from .backup_config import (
    _build_commands,
    _container_backup_root,
    _job_args,
    _load_config,
    _merge_request_config,
    _normalize_mirror_scopes,
    _option_flags,
    _save_bool_setting,
    _save_float_setting,
    _save_int_setting,
    _save_string_setting,
    _script_path,
    _host_project_root,
)
from .backup_models import (
    DOCKER_LOCAL_PREFIXES,
    KEY_BACKUP_ROOT,
    KEY_BASE_INTERVAL_HOURS,
    KEY_GOOGLE_DRIVE_RESOURCE_ROOT,
    KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED,
    KEY_MIN_FREE_GB,
    KEY_MIRROR_ROOT,
    KEY_MIRROR_SCOPES,
    KEY_REQUIRE_MIRROR,
    KEY_RETENTION_LOCAL_COUNT,
    KEY_RETENTION_MIRROR_COUNT,
    LOCALHOST_ADDRS,
    BackupJobRequest,
    GoogleDrivePrepareRequest,
    LocalRuntimeBackupConfig,
    LocalRuntimeBackupStatus,
    VerifyBackupRequest,
)
from .backup_state import (
    _call_backup_job,
    _device_node_available,
    _google_drive_sync_status,
    _latest_backup,
)


router = APIRouter()


def _is_localhost(request: Request) -> bool:
    def is_local_addr(value: str) -> bool:
        addr = value.strip()
        if addr.startswith("[") and addr.endswith("]"):
            addr = addr[1:-1]
        if addr.startswith("::ffff:"):
            addr = addr.removeprefix("::ffff:")
        if addr.count(":") == 1 and "." in addr.split(":", 1)[0]:
            addr = addr.split(":", 1)[0]
        return addr in LOCALHOST_ADDRS or addr.startswith(DOCKER_LOCAL_PREFIXES)

    client_ip = request.client.host if request.client else "unknown"
    if is_local_addr(client_ip):
        return True
    host = request.headers.get("host", "")
    if host.startswith(("localhost:", "127.0.0.1:", "[::1]:")):
        return True
    forwarded_for = request.headers.get("x-forwarded-for", "")
    real_ip = request.headers.get("x-real-ip", "")
    return any(is_local_addr(part) for part in [real_ip, *forwarded_for.split(",")])


@router.get("/backups/local-runtime", response_model=LocalRuntimeBackupStatus)
async def get_local_runtime_backup_status(include_plan: bool = Query(False)):
    config = _load_config()
    latest = _latest_backup()
    warnings: List[str] = []
    backup_root = _container_backup_root()
    backup_root_label = str(Path(config.backup_root).expanduser()) if config.backup_root else str(backup_root)
    policy: Dict[str, Any] = {
        "mode": "incremental_runtime_backup",
        "primary_root": backup_root_label,
        "mirror_root": config.mirror_root,
        "retention_local_count": config.retention_local_count,
        "retention_mirror_count": config.retention_mirror_count,
        "min_free_gb": config.min_free_gb,
        "require_mirror": config.require_mirror,
        "base_interval_hours": config.base_interval_hours,
        "mirror_scopes": _normalize_mirror_scopes(config.mirror_scopes),
    }
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
    can_run = False
    blocking_reasons: List[str] = []

    if not config.backup_root and not backup_root.exists():
        warnings.append(f"Backup root does not exist yet: {backup_root}")

    device_available = await _device_node_available()
    google_drive_sync = await _google_drive_sync_status(config, device_available)
    latest_job: Optional[Dict[str, Any]] = None
    if device_available:
        try:
            job_response = await _call_backup_job(_job_args("status", config), timeout_seconds=15)
            latest_job = job_response.get("job")
            if latest_job:
                latest_job["log_tail"] = job_response.get("log_tail") or []
        except HTTPException as exc:
            warnings.append(str(exc.detail))

        job_running = bool(latest_job and latest_job.get("state") == "running")
        if job_running:
            blocking_reasons.append("backup_job_running")
        elif config.require_mirror and not config.mirror_root:
            blocking_reasons.append("mirror_required_but_not_configured")
        elif include_plan:
            try:
                plan_response = await _call_backup_job(_job_args("plan", config), timeout_seconds=45)
                if isinstance(plan_response.get("policy"), dict):
                    policy = plan_response["policy"]
                    backup_root_label = str(policy.get("primary_root") or backup_root_label)
                primary_free_bytes = plan_response.get("primary_free_bytes")
                mirror_free_bytes = plan_response.get("mirror_free_bytes")
                postgres_archive_mode = plan_response.get("postgres_archive_mode")
                postgres_wal_ready_count = plan_response.get("postgres_wal_ready_count")
                postgres_wal_bytes = plan_response.get("postgres_wal_bytes")
                wal_archive_dir = plan_response.get("wal_archive_dir")
                wal_segment_count = plan_response.get("wal_segment_count")
                wal_archive_bytes = plan_response.get("wal_archive_bytes")
                base_backup_id = plan_response.get("base_backup_id")
                base_backup_created_at = plan_response.get("base_backup_created_at")
                base_backup_age_hours = plan_response.get("base_backup_age_hours")
                base_backup_required = plan_response.get("base_backup_required")
                latest_file_snapshot_id = plan_response.get("latest_file_snapshot_id")
                can_run = bool(plan_response.get("can_run"))
                blocking_reasons = [str(item) for item in plan_response.get("blocking_reasons") or []]
                warnings.extend(str(item) for item in plan_response.get("warnings") or [])
            except HTTPException as exc:
                warnings.append(str(exc.detail))
        else:
            can_run = True
        try:
            latest_response = await _call_backup_job(_job_args("latest-backup", config), timeout_seconds=15)
            latest = latest_response.get("latest_backup") or latest
        except HTTPException as exc:
            warnings.append(str(exc.detail))
    else:
        blocking_reasons.append("device_node_required")

    script_available = all(
        _script_path(name).is_file()
        for name in [
            "local_runtime_backup_job.py",
            "local_runtime_backup_policy.py",
            "local_runtime_incremental_backup.py",
        ]
    )
    verify_script_available = all(
        _script_path(name).is_file()
        for name in [
            "verify_local_runtime_backup.sh",
            "verify_local_runtime_incremental_backup.py",
        ]
    )
    if not script_available:
        blocking_reasons.append("backup_scripts_unavailable")
    if not verify_script_available:
        blocking_reasons.append("backup_verify_scripts_unavailable")

    return LocalRuntimeBackupStatus(
        config=config,
        backup_root=backup_root_label,
        policy=policy,
        primary_free_bytes=primary_free_bytes,
        mirror_free_bytes=mirror_free_bytes,
        postgres_archive_mode=postgres_archive_mode,
        postgres_wal_ready_count=postgres_wal_ready_count,
        postgres_wal_bytes=postgres_wal_bytes,
        wal_archive_dir=wal_archive_dir,
        wal_segment_count=wal_segment_count,
        wal_archive_bytes=wal_archive_bytes,
        base_backup_id=base_backup_id,
        base_backup_created_at=base_backup_created_at,
        base_backup_age_hours=base_backup_age_hours,
        base_backup_required=base_backup_required,
        latest_file_snapshot_id=latest_file_snapshot_id,
        can_run=can_run and script_available and verify_script_available,
        blocking_reasons=blocking_reasons,
        script_available=script_available,
        verify_script_available=verify_script_available,
        host_project_root=_host_project_root(),
        device_node_available=device_available,
        latest_backup=latest,
        latest_job=latest_job,
        commands=_build_commands(config, latest),
        google_drive_sync=google_drive_sync,
        warnings=warnings,
    )


@router.put("/backups/local-runtime/config", response_model=LocalRuntimeBackupStatus)
async def update_local_runtime_backup_config(config: LocalRuntimeBackupConfig):
    _save_string_setting(
        KEY_BACKUP_ROOT,
        config.backup_root.strip(),
        "Host primary root for verified local runtime backups",
    )
    _save_string_setting(
        KEY_MIRROR_ROOT,
        config.mirror_root.strip(),
        "Host mirror root for verified local runtime backups",
    )
    _save_int_setting(
        KEY_RETENTION_LOCAL_COUNT,
        config.retention_local_count,
        "Number of local runtime backups to retain",
    )
    _save_int_setting(
        KEY_RETENTION_MIRROR_COUNT,
        config.retention_mirror_count,
        "Number of mirrored local runtime backups to retain",
    )
    _save_float_setting(
        KEY_MIN_FREE_GB,
        config.min_free_gb,
        "Minimum free disk space in GB required before starting a backup",
    )
    _save_bool_setting(
        KEY_REQUIRE_MIRROR,
        config.require_mirror,
        "Require a writable mirror root before starting a local runtime backup",
    )
    _save_int_setting(
        KEY_BASE_INTERVAL_HOURS,
        config.base_interval_hours,
        "Maximum age in hours before creating a new physical base backup",
    )
    _save_string_setting(
        KEY_MIRROR_SCOPES,
        ",".join(_normalize_mirror_scopes(config.mirror_scopes)),
        "Comma-separated mirror data scopes for local runtime backup",
    )
    _save_bool_setting(
        KEY_GOOGLE_DRIVE_RESOURCE_SYNC_ENABLED,
        config.google_drive_resource_sync_enabled,
        "Enable Google Drive-backed local resource collaboration",
    )
    _save_string_setting(
        KEY_GOOGLE_DRIVE_RESOURCE_ROOT,
        config.google_drive_resource_root.strip(),
        "Host Google Drive root for local resource collaboration",
    )
    return await get_local_runtime_backup_status()


@router.post("/backups/local-runtime/dry-run")
async def dry_run_local_runtime_backup(request: Request, body: BackupJobRequest = BackupJobRequest()):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Backup controls are restricted to localhost")
    config = _merge_request_config(body)
    return await _call_backup_job(_job_args("dry-run", config), timeout_seconds=130)


@router.post("/backups/local-runtime/start")
async def start_local_runtime_backup(request: Request, body: BackupJobRequest = BackupJobRequest()):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Backup controls are restricted to localhost")
    config = _merge_request_config(body)
    return await _call_backup_job(_job_args("start", config), timeout_seconds=15)


@router.get("/backups/local-runtime/jobs/latest")
async def get_latest_local_runtime_backup_job():
    return await _call_backup_job(["status"], timeout_seconds=10)


@router.get("/backups/local-runtime/jobs/{job_id}")
async def get_local_runtime_backup_job(job_id: str):
    return await _call_backup_job(["status", "--job-id", job_id], timeout_seconds=10)


@router.post("/backups/local-runtime/verify")
async def verify_local_runtime_backup(request: Request, body: VerifyBackupRequest = VerifyBackupRequest()):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Backup controls are restricted to localhost")

    args = ["verify"]
    args.extend(_option_flags(_load_config()))
    if body.backup_dir:
        args.extend(["--backup-dir", body.backup_dir])
    return await _call_backup_job(args, timeout_seconds=1205)


@router.post("/backups/local-runtime/maintenance/verify-prune")
async def verify_and_prune_local_runtime_backup(
    request: Request,
    body: VerifyBackupRequest = VerifyBackupRequest(),
):
    if not _is_localhost(request):
        raise HTTPException(
            status_code=403,
            detail="Backup maintenance controls are restricted to localhost",
        )
    config = _load_config()
    args = _job_args("verify-prune", config)
    if body.backup_dir:
        args.extend(["--backup-dir", body.backup_dir])
    return await _call_backup_job(args, timeout_seconds=1205)


@router.post("/backups/local-runtime/google-drive/prepare")
async def prepare_google_drive_runtime_sync(
    request: Request,
    body: GoogleDrivePrepareRequest = GoogleDrivePrepareRequest(),
):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="Google Drive sync controls are restricted to localhost")

    config = _load_config()
    mirror_root = (body.mirror_root if body.mirror_root is not None else config.mirror_root).strip()
    resource_root = (
        body.resource_root
        if body.resource_root is not None
        else config.google_drive_resource_root
    ).strip()
    args = ["prepare-google-drive"]
    if mirror_root:
        args.extend(["--mirror-root", mirror_root])
    if resource_root:
        args.extend(["--resource-root", resource_root])
    return await _call_backup_job(args, timeout_seconds=30)
