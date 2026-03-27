from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

from capabilities.comfyui_runtime.services.workbench_summary import (
    build_workbench_summary,
    build_workbench_profiles,
    build_runtime_health,
    get_workbench_binding,
    list_workbench_runs,
)
from capabilities.comfyui_runtime.services.runtime_config import (
    ComfyUIPreviewRuntimeConfigService,
    derive_runtime_paths_from_install_path,
)

try:
    from backend.app.services.device_node_filesystem import (
        DeviceNodeError,
        get_device_node_filesystem,
    )
except ImportError:
    from app.services.device_node_filesystem import (
        DeviceNodeError,
        get_device_node_filesystem,
    )

router = APIRouter()
runtime_config_service: Optional[ComfyUIPreviewRuntimeConfigService] = None


class _InMemorySettingsStore:
    def __init__(self) -> None:
        self._settings: Dict[str, Any] = {}

    def get_setting(self, key: str):
        return self._settings.get(key)

    def save_setting(self, setting):
        self._settings[setting.key] = setting
        return setting


def _get_runtime_config_service() -> ComfyUIPreviewRuntimeConfigService:
    global runtime_config_service
    if runtime_config_service is not None:
        return runtime_config_service

    try:
        from backend.app.services.system_settings_store import SystemSettingsStore

        runtime_config_service = ComfyUIPreviewRuntimeConfigService(
            settings_store=SystemSettingsStore()
        )
    except Exception:
        runtime_config_service = ComfyUIPreviewRuntimeConfigService(
            settings_store=_InMemorySettingsStore(),
            environ={},
        )
    return runtime_config_service


class ComfyUIPreviewRuntimeUpdate(BaseModel):
    install_path: Optional[str] = Field(default=None, description="Base ComfyUI data path")
    main_py: Optional[str] = Field(default=None, description="Optional main.py override")
    python_bin: Optional[str] = Field(default=None, description="Optional Python binary override")
    log_file: Optional[str] = Field(default=None, description="Optional log file override")
    extra_model_paths_config: Optional[str] = Field(
        default=None,
        description="Optional extra_model_paths.yaml override",
    )
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    health_host: Optional[str] = Field(default=None)
    listen: Optional[str] = Field(default=None)
    clear: bool = Field(default=False, description="Clear all stored overrides")


class ComfyUIRuntimeValidateRequest(BaseModel):
    install_path: str = Field(..., description="Host ComfyUI install path to validate")


def _build_candidate_groups(install_path: str) -> Dict[str, List[str]]:
    derived = derive_runtime_paths_from_install_path(install_path)
    normalized = install_path.rstrip("/")
    return {
        "main_py": [
            derived["main_py"],
            f"{normalized}/Contents/Resources/ComfyUI/main.py",
        ],
        "python_bin": [
            derived["python_bin"],
            f"{normalized}/venv/bin/python",
            f"{normalized}/Contents/Resources/ComfyUI/.venv/bin/python",
        ],
        "extra_model_paths_config": [
            derived["extra_model_paths_config"],
            f"{normalized}/Contents/Resources/ComfyUI/extra_model_paths.yaml",
        ],
        "log_file": [derived["log_file"]],
        "models_dir": [f"{normalized}/models"],
    }


def _pick_detected_path(
    stats: Dict[str, Dict[str, Any]],
    candidates: List[str],
) -> Dict[str, str]:
    for candidate in candidates:
        info = stats.get(candidate, {})
        if info.get("exists"):
            return {
                "path": info.get("resolved_path") or candidate,
                "source": "detected_existing",
            }
    first_candidate = candidates[0] if candidates else ""
    return {
        "path": first_candidate,
        "source": "derived_by_convention" if first_candidate else "unset",
    }


@router.get("/status")
async def get_status():
    return {"status": "ok", "message": "ComfyUI Runtime Capability is loaded"}


@router.get("/runtime-config")
async def get_runtime_config() -> Dict[str, Any]:
    service = _get_runtime_config_service()
    stored = service.get_stored_config()
    effective = service.get_effective_config()
    return {
        "configured": stored,
        "effective": effective,
        "install_path_configured": effective["install_path_configured"],
    }


@router.get("/runtime-config/effective")
async def get_runtime_config_effective() -> Dict[str, Any]:
    return _get_runtime_config_service().get_effective_config()


@router.post("/runtime-config/validate-host-path")
async def validate_runtime_host_path(
    request: ComfyUIRuntimeValidateRequest,
) -> Dict[str, Any]:
    install_path = request.install_path.strip()
    if not install_path:
        return {
            "success": False,
            "status": "invalid",
            "detail": "install_path is required",
        }

    filesystem = get_device_node_filesystem()
    if not await filesystem.is_available():
        return {
            "success": False,
            "status": "invalid",
            "detail": "Device Node not reachable. Start it on host first.",
        }

    candidate_groups = _build_candidate_groups(install_path)
    all_paths = [install_path]
    for values in candidate_groups.values():
        all_paths.extend(values)

    try:
        stats = await filesystem.stat_paths(all_paths)
    except DeviceNodeError as exc:
        return {
            "success": False,
            "status": "invalid",
            "detail": str(exc),
        }

    root_stats = stats.get(install_path, {})
    exists = bool(root_stats.get("exists"))
    is_directory = bool(root_stats.get("is_directory"))
    readable = bool(root_stats.get("readable"))
    writable = bool(root_stats.get("writable"))

    detections = {
        key: _pick_detected_path(stats, values) for key, values in candidate_groups.items()
    }

    standard_main_py = candidate_groups["main_py"][0]
    existing_main_py = stats.get(standard_main_py, {}).get("exists", False)
    any_main_py = any(stats.get(path, {}).get("exists", False) for path in candidate_groups["main_py"])

    issues: List[str] = []
    guidance: List[str] = []

    if not exists:
        issues.append("指定路徑不存在。")
    if exists and not is_directory:
        issues.append("指定路徑不是資料夾。")
    if exists and is_directory and not readable:
        issues.append("指定路徑不可讀，無法掃描 ComfyUI 安裝內容。")
    if exists and is_directory and not writable:
        issues.append("指定路徑不可寫，ComfyUI base directory 無法安全寫入 logs/output/user。")
    if exists and is_directory and readable and not any_main_py:
        issues.append("找不到可辨識的 ComfyUI main.py。標準 repo 可直接指向根目錄；若是 App bundle 或分離式安裝，請填 main.py override。")
    if exists and is_directory and readable and not stats.get(detections["python_bin"]["path"], {}).get("exists", False):
        guidance.append("未找到 Python binary，若你的 ComfyUI 不在標準 .venv 位置，請填 Python override。")
    if exists and is_directory and readable and not stats.get(detections["extra_model_paths_config"]["path"], {}).get("exists", False):
        guidance.append("未找到 extra_model_paths.yaml；這不是硬錯誤，但若要掛載額外模型目錄，建議另行指定。")

    valid_access = exists and is_directory and readable and writable
    status = (
        "ready"
        if valid_access and existing_main_py
        else "needs_overrides"
        if valid_access
        else "invalid"
    )

    return {
        "success": True,
        "status": status,
        "valid_access": valid_access,
        "is_probable_comfyui": any_main_py,
        "install_path": install_path,
        "checks": {
            "requested_path": install_path,
            "resolved_path": root_stats.get("resolved_path") or install_path,
            "exists": exists,
            "is_directory": is_directory,
            "readable": readable,
            "writable": writable,
            "executable": bool(root_stats.get("executable")),
        },
        "detected": {
            "main_py": detections["main_py"],
            "python_bin": detections["python_bin"],
            "extra_model_paths_config": detections["extra_model_paths_config"],
            "log_file": detections["log_file"],
            "models_dir": detections["models_dir"],
            "standard_layout_ready": bool(existing_main_py),
        },
        "issues": issues,
        "guidance": guidance,
    }


@router.put("/runtime-config")
async def update_runtime_config(
    request: ComfyUIPreviewRuntimeUpdate,
) -> Dict[str, Any]:
    service = _get_runtime_config_service()
    if request.clear:
        service.clear_config()
    else:
        service.update_config(request.model_dump(exclude={"clear"}))

    stored = service.get_stored_config()
    effective = service.get_effective_config()
    return {
        "success": True,
        "message": (
            "ComfyUI runtime 設定已清除"
            if request.clear
            else "ComfyUI runtime 設定已儲存"
        ),
        "configured": stored,
        "effective": effective,
        "install_path_configured": effective["install_path_configured"],
    }


@router.get("/workbench/summary")
async def get_workbench_summary(
    project_id: Optional[str] = Query(default=None),
    comfyui_url: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-Id"),
):
    return await build_workbench_summary(
        tenant_id=x_tenant_id,
        project_id=project_id,
        comfyui_url=comfyui_url,
        limit=limit,
    )


@router.get("/workbench/runs")
async def get_workbench_runs(
    project_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    include_scene_projections: bool = Query(default=False),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-Id"),
):
    runs = list_workbench_runs(
        tenant_id=x_tenant_id,
        project_id=project_id,
        limit=limit,
        include_scene_projections=include_scene_projections,
    )
    return {"runs": runs, "count": len(runs)}


@router.get("/workbench/bindings")
async def get_workbench_bindings(
    project_id: str,
    run_id: str,
    scene_id: Optional[str] = Query(default=None),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-Id"),
):
    return get_workbench_binding(
        tenant_id=x_tenant_id,
        project_id=project_id,
        run_id=run_id,
        scene_id=scene_id,
    )


@router.get("/workbench/profiles")
async def get_workbench_profiles(
    comfyui_url: Optional[str] = Query(default=None),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-Id"),
):
    return await build_workbench_profiles(
        tenant_id=x_tenant_id,
        comfyui_url=comfyui_url,
    )


@router.get("/workbench/runtime-health")
async def get_workbench_runtime_health(
    comfyui_url: Optional[str] = Query(default=None),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-Id"),
):
    return await build_runtime_health(
        tenant_id=x_tenant_id,
        comfyui_url=comfyui_url,
    )
