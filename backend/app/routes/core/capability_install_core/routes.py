import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)

from .paths import (
    OVERWRITE_CONFIRMATION_PHRASE,
    _parse_bool_flag,
    _require_control_plane_install,
    _require_explicit_overwrite_confirmation,
    _resolve_runtime_temp_dir,
    _ensure_sys_path,
)
from .pipeline import run_install_pipeline
from .schemas import InstallFromCloudRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])


@router.post("/install-from-file", response_model=Dict[str, Any])
async def install_from_file(
    fastapi_request: Request,
    file: UploadFile = File(...),
    allow_overwrite: str = Form("false"),
    overwrite_confirmation: str = Form(""),
    overwrite_review_confirmation: str = Form(""),
    profile_id: str = Query(
        "default-user", description="User profile ID for role mapping"
    ),
):
    """
    Install capability package from .mindpack file

    Supports offline installation of capability packages.
    Validates manifest, checks conflicts, and installs to capabilities directory.
    """
    _require_control_plane_install("install-from-file")

    if not file.filename.endswith(".mindpack"):
        raise HTTPException(status_code=400, detail="File must be a .mindpack file")

    overwrite = _parse_bool_flag(allow_overwrite)
    _require_explicit_overwrite_confirmation(
        allow_overwrite=overwrite,
        overwrite_confirmation=overwrite_confirmation,
    )

    temp_dir = _resolve_runtime_temp_dir()
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".mindpack", dir=temp_dir
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = await run_install_pipeline(
            fastapi_app=fastapi_request.app,
            mindpack_path=tmp_path,
            allow_overwrite=overwrite,
            overwrite_review_confirmation=overwrite_review_confirmation,
            source_label="install-from-file",
            extra_metadata={"installed_from_file": True},
        )

        return {
            "success": True,
            "capability_id": result.capability_code,
            "version": result.version,
            "message": f"Successfully installed {result.capability_code} v{result.version}",
            "warnings": result.warnings,
            "activation": result.activation,
            "validation": result.validation,
            "restart_required": result.restart_required,
            "restart_triggered": result.restart_triggered,
            "hot_reload": result.hot_reload_result,
            "webhook": result.webhook_result,
        }
    except HTTPException:
        raise
    except ImportError as exc:
        logger.error(f"Import error in install_from_file: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to import capability installer: {exc}"
        )
    except Exception as exc:
        logger.error(f"Installation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Installation failed: {exc}")
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ------------------------------------------------------------------
# Route: install-from-cloud
# ------------------------------------------------------------------


@router.post("/install-from-cloud", response_model=Dict[str, Any])
async def install_from_cloud(
    fastapi_request: Request,
    request: InstallFromCloudRequest,
    profile_id: str = Query(
        "default-user", description="User profile ID for role mapping"
    ),
    allow_overwrite: str = Query(
        "false", description="Force install even if local modifications detected"
    ),
    overwrite_confirmation: str = Query(
        "", description="Explicit confirmation phrase required when allow_overwrite=true"
    ),
    overwrite_review_confirmation: str = Query(
        "",
        description=(
            "Explicit confirmation phrase required after reviewing local diff conflicts"
        ),
    ),
):
    """
    Install capability pack from cloud provider

    Downloads pack from configured cloud provider and installs it locally.
    Supports any provider that implements the CloudProvider interface.
    """
    try:
        _require_control_plane_install("install-from-cloud")

        overwrite = _parse_bool_flag(allow_overwrite)
        _require_explicit_overwrite_confirmation(
            allow_overwrite=overwrite,
            overwrite_confirmation=overwrite_confirmation,
        )

        _ensure_sys_path()
        from app.services.cloud_extension_manager import CloudExtensionManager
        from app.services.pack_download_service import get_pack_download_service
        from app.routes.core.cloud_providers import get_cloud_manager

        cloud_manager = get_cloud_manager()

        provider = cloud_manager.get_provider(request.provider_id)
        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"Provider '{request.provider_id}' not found. Please configure it first.",
            )

        if not provider.is_configured():
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{request.provider_id}' is not configured. Please configure it first.",
            )

        if not hasattr(provider, "get_download_link"):
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{request.provider_id}' does not support pack downloads",
            )

        download_service = get_pack_download_service()
        success, pack_file, error_msg = await download_service.download_pack(
            provider=provider,
            pack_ref=request.pack_ref,
            verify_checksum=request.verify_checksum,
        )

        if not success:
            raise HTTPException(
                status_code=400, detail=f"Failed to download pack: {error_msg}"
            )
        if not pack_file:
            raise HTTPException(
                status_code=500, detail="Download succeeded but pack file not returned"
            )

        try:
            result = await run_install_pipeline(
                fastapi_app=fastapi_request.app,
                mindpack_path=pack_file,
                allow_overwrite=overwrite,
                overwrite_review_confirmation=overwrite_review_confirmation,
                source_label="install-from-cloud",
                extra_metadata={
                    "installed_from_cloud": True,
                    "provider_id": request.provider_id,
                    "pack_ref": request.pack_ref,
                },
            )

            return {
                "success": True,
                "capability_id": result.capability_code,
                "version": result.pack_metadata.get("version", "1.0.0"),
                "message": f"Successfully installed {result.capability_code} from {request.provider_id}",
                "warnings": result.warnings,
                "activation": result.activation,
                "validation": result.validation,
                "provider_id": request.provider_id,
                "pack_ref": request.pack_ref,
                "restart_required": result.restart_required,
                "restart_triggered": result.restart_triggered,
                "hot_reload": result.hot_reload_result,
                "webhook": result.webhook_result,
            }
        finally:
            if pack_file and pack_file.exists():
                try:
                    pack_file.unlink()
                except Exception as exc:
                    logger.warning(f"Failed to clean up temporary pack file: {exc}")

    except HTTPException:
        raise
    except ImportError as exc:
        logger.error(f"Import error in install_from_cloud: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to import required modules: {exc}"
        )
    except Exception as exc:
        logger.error(f"Cloud installation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cloud installation failed: {exc}")
