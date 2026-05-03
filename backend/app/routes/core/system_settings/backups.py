"""
Local runtime backup settings and controls.

The actual backup logic lives in scripts/backup_local_runtime.sh. These routes
surface status/configuration to the settings UI and delegate long-running host
execution to Device Node.
"""

from __future__ import annotations

import json
import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.models.system_settings import SettingType, SystemSetting
from .shared import settings_store


router = APIRouter()

BACKUP_CATEGORY = "backup"
KEY_INCLUDE_LOGS = "local_runtime_backup.include_logs"
KEY_INCLUDE_E2E_TRACES = "local_runtime_backup.include_e2e_traces"

LOCALHOST_ADDRS = {"127.0.0.1", "localhost", "::1", "unknown", "testclient"}
DOCKER_LOCAL_PREFIXES = ("172.", "192.168.65.")


class LocalRuntimeBackupConfig(BaseModel):
    include_logs: bool = False
    include_e2e_traces: bool = False


class LocalRuntimeBackupStatus(BaseModel):
    config: LocalRuntimeBackupConfig
    backup_root: str
    script_available: bool
    verify_script_available: bool
    host_project_root: str
    device_node_available: bool
    latest_backup: Optional[Dict[str, Any]] = None
    latest_job: Optional[Dict[str, Any]] = None
    commands: Dict[str, str]
    warnings: List[str] = Field(default_factory=list)


class BackupJobRequest(BaseModel):
    include_logs: Optional[bool] = None
    include_e2e_traces: Optional[bool] = None


class VerifyBackupRequest(BaseModel):
    backup_dir: Optional[str] = None


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


def _container_backup_root() -> Path:
    data_dir = Path(os.getenv("DATA_DIR") or "/app/data")
    return Path(os.getenv("LOCAL_CORE_BACKUP_ROOT_CONTAINER") or data_dir / "backups" / "local-runtime")


def _host_project_root() -> str:
    return (
        os.getenv("LOCAL_CORE_PROJECT_ROOT")
        or os.getenv("HOST_PROJECT_PATH")
        or ""
    )


def _script_path(name: str) -> Path:
    return Path("/app/scripts") / name


def _get_bool(key: str, default: bool = False) -> bool:
    value = settings_store.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _load_config() -> LocalRuntimeBackupConfig:
    return LocalRuntimeBackupConfig(
        include_logs=_get_bool(KEY_INCLUDE_LOGS),
        include_e2e_traces=_get_bool(KEY_INCLUDE_E2E_TRACES),
    )


def _save_bool_setting(key: str, value: bool, description: str) -> None:
    settings_store.save_setting(
        SystemSetting(
            key=key,
            value=value,
            value_type=SettingType.BOOLEAN,
            category=BACKUP_CATEGORY,
            description=description,
        )
    )


def _option_flags(config: LocalRuntimeBackupConfig) -> List[str]:
    flags: List[str] = []
    if config.include_logs:
        flags.append("--include-logs")
    if config.include_e2e_traces:
        flags.append("--include-e2e-traces")
    return flags


def _command(parts: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _build_commands(config: LocalRuntimeBackupConfig, latest_backup: Optional[Dict[str, Any]]) -> Dict[str, str]:
    root = _host_project_root()
    if not root:
        hint = "Set LOCAL_CORE_PROJECT_ROOT to the host checkout path."
        return {
            "create": hint,
            "dry_run": hint,
            "verify_latest": hint,
        }
    flags = _option_flags(config)
    base = f"cd {_command([root])}"
    create = f"{base} && {_command(['scripts/backup_local_runtime.sh', *flags])}"
    dry_run = f"{base} && {_command(['scripts/backup_local_runtime.sh', *flags, '--dry-run'])}"
    verify_target = latest_backup.get("host_backup_dir") if latest_backup else "<backup-dir>"
    verify = f"{base} && {_command(['scripts/verify_local_runtime_backup.sh', str(verify_target)])}"
    return {
        "create": create,
        "dry_run": dry_run,
        "verify_latest": verify,
    }


def _profile_state_summary(backup_dir: Path) -> Optional[Dict[str, Any]]:
    report_path = backup_dir / "metadata" / "profile-state-report.json"
    if not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "error": f"{type(exc).__name__}: {exc}"}

    profiles = report.get("profiles") or []
    invalid = [item for item in profiles if not item.get("valid")]
    return {
        "valid": not invalid,
        "profiles": len(profiles),
        "invalid_profiles": len(invalid),
        "invalid": invalid,
    }


def _parse_backup_manifest(manifest_path: Path) -> Optional[Dict[str, Any]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    backup_dir = manifest_path.parent
    artifacts = manifest.get("artifacts") or []
    total_bytes = sum(int(item.get("bytes") or 0) for item in artifacts if isinstance(item, dict))
    backup_name = str(manifest.get("backup_name") or backup_dir.name)
    data_host_dir = manifest.get("data_host_dir")
    host_backup_dir = (
        str(Path(str(data_host_dir)) / "backups" / "local-runtime" / backup_name)
        if data_host_dir
        else str(backup_dir)
    )
    created_at = manifest.get("created_at")

    return {
        "backup_name": backup_name,
        "created_at": created_at,
        "path": str(backup_dir),
        "host_backup_dir": host_backup_dir,
        "schema_version": manifest.get("schema_version"),
        "git_commit": manifest.get("git_commit"),
        "options": manifest.get("options") or {},
        "artifact_count": len(artifacts),
        "total_bytes": total_bytes,
        "profile_state": _profile_state_summary(backup_dir),
        "manifest_mtime": manifest_path.stat().st_mtime,
    }


def _latest_backup() -> Optional[Dict[str, Any]]:
    backup_root = _container_backup_root()
    if not backup_root.is_dir():
        return None

    backups: List[Dict[str, Any]] = []
    for manifest_path in backup_root.glob("*/manifest.json"):
        parsed = _parse_backup_manifest(manifest_path)
        if parsed:
            backups.append(parsed)

    if not backups:
        return None

    def sort_key(item: Dict[str, Any]) -> Any:
        created_at = item.get("created_at")
        if isinstance(created_at, str):
            try:
                return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        return item.get("manifest_mtime") or 0

    latest = max(backups, key=sort_key)
    latest.pop("manifest_mtime", None)
    return latest


async def _device_node_available() -> bool:
    device_node_url = os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{device_node_url}/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers={"Content-Type": "application/json", "User-Agent": "Mindscape-LocalCore/1.0"},
            )
        return 200 <= response.status_code < 300
    except Exception:
        return False


async def _call_backup_job(args: List[str], timeout_seconds: float = 30.0) -> Dict[str, Any]:
    device_node_url = os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100")
    host_project_root = _host_project_root()
    if not host_project_root:
        raise HTTPException(
            status_code=400,
            detail="LOCAL_CORE_PROJECT_ROOT must be set to the host checkout path before running backup controls.",
        )
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "shell_execute",
            "arguments": {
                "command": "python3",
                "args": ["scripts/local_runtime_backup_job.py", *args],
                "cwd": host_project_root,
                "timeout_ms": int(timeout_seconds * 1000),
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds + 5) as client:
            response = await client.post(
                f"{device_node_url}/mcp",
                json=mcp_request,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mindscape-LocalCore/1.0",
                    "X-Request-Source": "local-runtime-backup",
                },
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Device Node not reachable. Start it on host before running backup controls.",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Device Node backup command timed out")

    try:
        result = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Invalid Device Node response: {exc}")

    if response.status_code >= 400 or result.get("error"):
        error = result.get("error") or {}
        raise HTTPException(
            status_code=502,
            detail=error.get("message") or f"Device Node returned HTTP {response.status_code}",
        )

    content = result.get("result", {}).get("content") or []
    text = content[0].get("text") if content else "{}"
    try:
        return json.loads(text)
    except Exception:
        return {"raw": text}


def _merge_request_config(request: BackupJobRequest) -> LocalRuntimeBackupConfig:
    config = _load_config()
    return LocalRuntimeBackupConfig(
        include_logs=config.include_logs if request.include_logs is None else request.include_logs,
        include_e2e_traces=(
            config.include_e2e_traces
            if request.include_e2e_traces is None
            else request.include_e2e_traces
        ),
    )


def _job_args(command: str, config: LocalRuntimeBackupConfig) -> List[str]:
    args = [command]
    args.extend(_option_flags(config))
    return args


@router.get("/backups/local-runtime", response_model=LocalRuntimeBackupStatus)
async def get_local_runtime_backup_status():
    config = _load_config()
    latest = _latest_backup()
    warnings: List[str] = []
    backup_root = _container_backup_root()

    if not backup_root.exists():
        warnings.append(f"Backup root does not exist yet: {backup_root}")

    device_available = await _device_node_available()
    latest_job: Optional[Dict[str, Any]] = None
    if device_available:
        try:
            job_response = await _call_backup_job(["status"], timeout_seconds=10)
            latest_job = job_response.get("job")
            if latest_job:
                latest_job["log_tail"] = job_response.get("log_tail") or []
        except HTTPException as exc:
            warnings.append(str(exc.detail))

    return LocalRuntimeBackupStatus(
        config=config,
        backup_root=str(backup_root),
        script_available=_script_path("backup_local_runtime.sh").is_file(),
        verify_script_available=_script_path("verify_local_runtime_backup.sh").is_file(),
        host_project_root=_host_project_root(),
        device_node_available=device_available,
        latest_backup=latest,
        latest_job=latest_job,
        commands=_build_commands(config, latest),
        warnings=warnings,
    )


@router.put("/backups/local-runtime/config", response_model=LocalRuntimeBackupStatus)
async def update_local_runtime_backup_config(config: LocalRuntimeBackupConfig):
    _save_bool_setting(KEY_INCLUDE_LOGS, config.include_logs, "Include /app/logs in local runtime backups")
    _save_bool_setting(
        KEY_INCLUDE_E2E_TRACES,
        config.include_e2e_traces,
        "Include e2e trace artifacts in local runtime backups",
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
    if body.backup_dir:
        args.extend(["--backup-dir", body.backup_dir])
    return await _call_backup_job(args, timeout_seconds=1205)
