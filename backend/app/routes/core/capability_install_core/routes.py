import logging
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

from backend.app.database.write_readiness import DatabaseWriteNotReadyError
from backend.app.services.capability_install_jobs import CapabilityInstallJobService
from backend.app.services.runtime_database_incident_gate import (
    RuntimeDatabaseMutationBlocked,
    require_runtime_database_mutation_allowed,
)

from .paths import (
    OVERWRITE_CONFIRMATION_PHRASE,
    _parse_bool_flag,
    _require_control_plane_install,
    _require_explicit_overwrite_confirmation,
    _ensure_sys_path,
)
from .schemas import InstallFromCloudRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])


def _raise_db_not_ready(exc: DatabaseWriteNotReadyError) -> None:
    raise HTTPException(
        status_code=503,
        detail={
            "error": "postgres_write_not_ready",
            "reason": exc.readiness.reason,
            "retry_after_seconds": exc.readiness.retry_after_seconds,
        },
        headers={"Retry-After": str(exc.readiness.retry_after_seconds)},
    )


def _require_install_mutation_allowed(operation: str) -> None:
    try:
        require_runtime_database_mutation_allowed(operation)
    except RuntimeDatabaseMutationBlocked as exc:
        decision = exc.decision
        raise HTTPException(
            status_code=503,
            detail={
                "error": decision.reason,
                "incident_id": decision.incident_id,
                "retry_after_seconds": decision.retry_after_seconds,
            },
            headers={"Retry-After": str(decision.retry_after_seconds)},
        ) from exc


@router.post("/install-from-file", response_model=Dict[str, Any])
async def install_from_file(
    fastapi_request: Request,
    file: UploadFile = File(...),
    allow_overwrite: str = Form("false"),
    overwrite_confirmation: str = Form(""),
    overwrite_review_confirmation: str = Form(""),
    source_commit: str = Form(""),
    backout_from_install_id: str = Form(""),
    backout_artifact_sha256: str = Form(""),
    backout_target_version: str = Form(""),
    backout_schema_compatibility_receipt: str = Form(""),
    backout_owner_approval: str = Form(""),
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
    _require_install_mutation_allowed("capability_install_intake:file")

    if not file.filename.endswith(".mindpack"):
        raise HTTPException(status_code=400, detail="File must be a .mindpack file")

    overwrite = _parse_bool_flag(allow_overwrite)
    _require_explicit_overwrite_confirmation(
        allow_overwrite=overwrite,
        overwrite_confirmation=overwrite_confirmation,
    )

    try:
        content = await file.read()
        backout_values = {
            "backout_from_install_id": backout_from_install_id.strip(),
            "artifact_sha256": backout_artifact_sha256.strip().lower(),
            "target_version": backout_target_version.strip(),
            "schema_compatibility_receipt": (
                backout_schema_compatibility_receipt.strip()
            ),
            "owner_approval": backout_owner_approval.strip(),
        }
        supplied = [bool(value) for value in backout_values.values()]
        if any(supplied) and not all(supplied):
            raise HTTPException(
                status_code=400,
                detail="complete_backout_receipt_required",
            )
        if backout_values["artifact_sha256"] and (
            len(backout_values["artifact_sha256"]) != 64
            or any(
                char not in "0123456789abcdef"
                for char in backout_values["artifact_sha256"]
            )
        ):
            raise HTTPException(status_code=400, detail="invalid_backout_artifact_sha256")
        job = CapabilityInstallJobService().create_file_upload_job(
            filename=file.filename,
            content=content,
            allow_overwrite=overwrite,
            overwrite_review_confirmation=overwrite_review_confirmation,
            profile_id=profile_id,
            source_commit=source_commit,
            backout_receipt=backout_values if all(supplied) else None,
        )
        return {
            "success": True,
            "accepted": True,
            "install_id": job["install_id"],
            "state": job["state"],
            "status_url": job["status_url"],
            "message": "Capability install job accepted",
        }
    except DatabaseWriteNotReadyError as exc:
        _raise_db_not_ready(exc)
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
        _require_install_mutation_allowed("capability_install_intake:cloud")

        overwrite = _parse_bool_flag(allow_overwrite)
        _require_explicit_overwrite_confirmation(
            allow_overwrite=overwrite,
            overwrite_confirmation=overwrite_confirmation,
        )

        _ensure_sys_path()
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

        job = CapabilityInstallJobService().create_cloud_pack_job(
            provider_id=request.provider_id,
            pack_ref=request.pack_ref,
            verify_checksum=request.verify_checksum,
            allow_overwrite=overwrite,
            overwrite_review_confirmation=overwrite_review_confirmation,
            profile_id=profile_id,
            backout_receipt=(
                request.backout_receipt.model_dump()
                if request.backout_receipt is not None
                else None
            ),
        )
        return {
            "success": True,
            "accepted": True,
            "install_id": job["install_id"],
            "state": job["state"],
            "status_url": job["status_url"],
            "provider_id": request.provider_id,
            "pack_ref": request.pack_ref,
            "message": "Cloud capability install job accepted",
        }

    except DatabaseWriteNotReadyError as exc:
        _raise_db_not_ready(exc)
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


@router.get("/install-jobs/{install_id}", response_model=Dict[str, Any])
async def get_install_job_status(install_id: str):
    try:
        job = CapabilityInstallJobService().get_job(install_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Install job not found")
        return job
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to load install job %s: %s", install_id, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load install job: {exc}",
        )
