"""
Capability Install Routes

Handles .mindpack file installation and cloud pack installation.
Extracted from capability_packs.py for maintainability.

Shared pipeline logic lives in ``run_install_pipeline`` to avoid duplication
between the file-based and cloud-based install endpoints.
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field
from typing import Dict, Any

from app.services.stores.installed_packs_store import InstalledPacksStore
from app.services.restart_webhook import get_restart_webhook_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])

installed_packs_store = InstalledPacksStore()


def _utc_now():
    """Return timezone-aware UTC now."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# Resolve local-core root (shared helper)
# ------------------------------------------------------------------


def _resolve_local_core_root() -> Path:
    """Resolve workspace root from current file location."""
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _ensure_sys_path():
    """Add backend dir to sys.path if needed."""
    import sys

    backend_dir = str(Path(__file__).resolve().parent.parent.parent)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)


def _supports_file_touch_reload() -> bool:
    """
    Detect whether touching a watched file can actually restart backend.

    We only auto-report restart_triggered=true when uvicorn is running with --reload.
    """
    for proc_cmdline in ("/proc/1/cmdline", "/proc/self/cmdline"):
        try:
            raw = Path(proc_cmdline).read_bytes()
            if b"--reload" in raw:
                return True
        except Exception:
            continue
    return False


# ------------------------------------------------------------------
# Shared install pipeline
# ------------------------------------------------------------------


@dataclass
class InstallPipelineResult:
    """Aggregated result from ``run_install_pipeline``."""

    success: bool = False
    capability_code: Optional[str] = None
    version: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    restart_required: bool = True
    restart_triggered: bool = False
    hot_reload_result: Any = None
    webhook_result: Any = None
    pack_metadata: Dict[str, Any] = field(default_factory=dict)


async def run_install_pipeline(
    *,
    fastapi_app,
    mindpack_path: Path,
    allow_overwrite: bool,
    source_label: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> InstallPipelineResult:
    """
    Shared install pipeline for both file-based and cloud-based installs.

    Steps:
      1. Extract mindpack
      2. Load & validate manifest
      2.5 Dirty-state check
      3. Install playbooks
      4. Install runtime assets + migrations
      5. Post-install hooks
      6. Reload registry / hot-reload
      7. Register pack in DB
      8. Webhook notification
      9. Record file hashes

    Args:
        fastapi_app:      The FastAPI ``app`` instance (for hot-reload).
        mindpack_path:    Path to the ``.mindpack`` file.
        allow_overwrite:  If True, skip dirty-state guard.
        source_label:     Human-readable source (e.g. ``"install-from-file"``).
        extra_metadata:   Extra fields merged into ``pack_metadata``.

    Returns:
        :class:`InstallPipelineResult`.

    Raises:
        HTTPException on validation or install failure.
    """
    _ensure_sys_path()

    from app.services.mindpack_extractor import MindpackExtractor
    from app.services.manifest_validator import ManifestValidator
    from app.services.playbook_installer import PlaybookInstaller
    from app.services.runtime_assets_installer import RuntimeAssetsInstaller
    from app.services.post_install import PostInstallHandler
    from app.services.install_result import InstallResult

    local_core_root = _resolve_local_core_root()
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    specs_dir = local_core_root / "backend" / "playbooks" / "specs"
    i18n_base_dir = local_core_root / "backend" / "i18n" / "playbooks"

    pipeline = InstallPipelineResult()

    # 1. Extract mindpack
    extractor = MindpackExtractor(local_core_root)
    extract_ok, temp_dir, capability_code, cap_dir = extractor.extract(mindpack_path)

    if not extract_ok or not capability_code or not cap_dir:
        raise HTTPException(
            status_code=400,
            detail="Failed to extract mindpack file or capability code not found",
        )

    pipeline.capability_code = capability_code

    try:
        # 2. Load & validate manifest
        manifest_path = cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            raise HTTPException(
                status_code=400, detail="manifest.yaml not found in mindpack"
            )

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Failed to parse manifest: {exc}"
            )

        pipeline.version = manifest.get("version", "1.0.0")

        validator = ManifestValidator(local_core_root)
        skip_validation = os.getenv("MINDSCAPE_SKIP_VALIDATION", "0") == "1"
        is_valid, validation_errors, validation_warnings = validator.validate(
            manifest_path, cap_dir, skip_validation=skip_validation
        )
        if not is_valid and not skip_validation:
            raise HTTPException(
                status_code=400,
                detail=f"Manifest validation failed: {validation_errors}",
            )

        # 2.5. Dirty-state check
        existing_cap_dir = capabilities_dir / capability_code
        if existing_cap_dir.exists():
            try:
                from app.services.install_integrity import check_dirty_state

                dirty = check_dirty_state(existing_cap_dir)
                if dirty.is_dirty and not allow_overwrite:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "local_modifications_detected",
                            "message": (
                                f"{capability_code}: {len(dirty.modified)} modified, "
                                f"{len(dirty.added)} added, {len(dirty.deleted)} deleted "
                                f"since v{dirty.installed_version} install"
                            ),
                            "installed_version": dirty.installed_version,
                            "installed_at": dirty.installed_at,
                            "incoming_version": pipeline.version,
                            "modified": dirty.modified,
                            "added": dirty.added,
                            "deleted": dirty.deleted,
                            "summary": dirty.summary(),
                            "hint": "Set allow_overwrite=true to force install",
                        },
                    )
                elif dirty.is_dirty:
                    logger.warning(
                        "Force overwriting %s with local modifications: %s",
                        capability_code,
                        dirty.summary(),
                    )
            except ImportError:
                logger.warning(
                    "install_integrity module not available, skipping dirty check"
                )

        # 3. Install playbooks + runtime
        result = InstallResult(capability_code=capability_code)
        result.warnings.extend(validation_warnings)

        playbook_installer = PlaybookInstaller()
        playbook_installer.capabilities_dir = capabilities_dir
        playbook_installer.specs_dir = specs_dir
        playbook_installer.i18n_base_dir = i18n_base_dir
        playbook_installer.local_core_root = local_core_root
        playbook_installer._install_playbooks(
            cap_dir, capability_code, manifest, result
        )

        runtime_installer = RuntimeAssetsInstaller(
            local_core_root=local_core_root, capabilities_dir=capabilities_dir
        )
        runtime_installer.install_all(
            cap_dir, capability_code, manifest, result, temp_dir
        )

        # Migrations
        runtime_installer.execute_migrations(capability_code, result)
        if hasattr(result, "migration_status") and result.migration_status:
            mig = result.migration_status.get(capability_code)
            if mig in ("failed", "error"):
                result.add_error(
                    f"Migration execution failed for {capability_code}: {mig}"
                )
            elif mig == "applied":
                logger.info(f"Successfully executed migrations for {capability_code}")
        else:
            logger.warning(f"Migration status not available for {capability_code}")

        # Post-install hooks
        post_handler = PostInstallHandler(
            local_core_root=local_core_root,
            capabilities_dir=capabilities_dir,
            specs_dir=specs_dir,
            validate_tools_direct_call_func=playbook_installer._validate_tools_direct_call,
        )
        post_handler.run_all(cap_dir, capability_code, manifest, result)

        # 4. Reload capability registry
        hot_reload_performed = False
        try:
            from app.capabilities.registry import get_registry, load_capabilities
            from app.services.capability_reload_manager import (
                hot_reload_enabled,
                reload_capability_routes,
            )
            from starlette.concurrency import run_in_threadpool

            registry = get_registry()
            if hasattr(registry, "_capabilities_cache"):
                registry._capabilities_cache.clear()
            if hasattr(registry, "_tools_cache"):
                registry._tools_cache.clear()

            if hot_reload_enabled():
                pipeline.hot_reload_result = await run_in_threadpool(
                    reload_capability_routes,
                    fastapi_app,
                    f"{source_label}:{capability_code}",
                )
                hot_reload_performed = True
                logger.info(f"Hot reload completed for {capability_code}")
            else:
                load_capabilities(reset=True)
                logger.info(f"Reloaded capability registry for {capability_code}")
        except Exception as exc:
            logger.warning(f"Failed to reload capability registry/routes: {exc}")
            result.add_warning(f"Failed to reload capability registry/routes: {exc}")
            try:
                from app.capabilities.registry import load_capabilities

                load_capabilities(reset=True)
            except Exception:
                pass

        # 5. Dev-mode reload trigger
        pipeline.restart_required = True
        env = os.getenv("ENVIRONMENT", "development")

        if hot_reload_performed:
            pipeline.restart_required = False
        elif env in ("development", "dev"):
            if _supports_file_touch_reload():
                try:
                    trigger = Path("/app/backend/app/capabilities/.reload_trigger")
                    trigger.touch()
                    pipeline.restart_triggered = True
                    pipeline.restart_required = False
                    logger.info(f"Reload triggered for {capability_code} via file touch")
                except Exception as exc:
                    logger.warning(f"Failed to trigger reload: {exc}")
                    result.add_warning(f"Restart required - auto-trigger failed: {exc}")
            else:
                result.add_warning(
                    "Backend is not running with --reload; auto file-touch restart skipped."
                )
                logger.info(
                    "Auto file-touch restart skipped for %s: --reload not detected",
                    capability_code,
                )

        # Check for errors
        if result.has_errors():
            raise HTTPException(
                status_code=400,
                detail=result.errors[0] if result.errors else "Installation failed",
            )

        # 6. Register in installed_packs table
        correct_backend = local_core_root / "backend"
        target_dir = correct_backend / "app" / "capabilities" / capability_code

        pack_metadata = {"version": pipeline.version}
        if extra_metadata:
            pack_metadata.update(extra_metadata)

        installed_manifest_path = target_dir / "manifest.yaml"
        if installed_manifest_path.exists():
            try:
                with open(installed_manifest_path, "r", encoding="utf-8") as f:
                    inst_manifest = yaml.safe_load(f)
                pack_metadata["side_effect_level"] = inst_manifest.get(
                    "side_effect_level"
                )
                pack_metadata["version"] = inst_manifest.get(
                    "version", pipeline.version
                )
            except Exception:
                pass

        try:
            installed_packs_store.upsert_pack(
                pack_id=capability_code,
                installed_at=_utc_now(),
                enabled=True,
                metadata=pack_metadata,
            )
        except Exception as exc:
            logger.warning(f"Failed to register pack in database: {exc}")

        pipeline.pack_metadata = pack_metadata

        # 7. Webhook notification
        if pipeline.restart_required:
            try:
                webhook_service = get_restart_webhook_service()
                if webhook_service.is_configured():
                    from app.routes.core.admin_reload import CapabilityValidator

                    cap_validator = CapabilityValidator(
                        [Path("/app/backend/app/capabilities")]
                    )
                    validation = cap_validator.validate_all()
                    webhook_kwargs = {
                        "capability_code": capability_code,
                        "validation_passed": validation["valid"],
                        "version": pack_metadata.get("version", "1.0.0"),
                    }
                    if extra_metadata:
                        webhook_kwargs["extra_data"] = extra_metadata
                    pipeline.webhook_result = (
                        await webhook_service.notify_restart_required(**webhook_kwargs)
                    )
            except Exception as exc:
                logger.warning(f"Webhook notification failed: {exc}")

        # 8. Record file hashes for dirty-state detection
        try:
            from app.services.install_integrity import (
                compute_dir_hashes,
                save_install_manifest,
            )

            installed_cap_dir = capabilities_dir / capability_code
            if installed_cap_dir.exists():
                hashes = compute_dir_hashes(installed_cap_dir)
                save_install_manifest(
                    installed_cap_dir,
                    pack_metadata.get("version", "1.0.0"),
                    hashes,
                )
        except Exception as exc:
            logger.warning(f"Failed to record install hashes: {exc}")

        pipeline.success = True
        pipeline.warnings = result.warnings
        return pipeline

    finally:
        # Clean up temp extraction directory
        if temp_dir and temp_dir.exists():
            import shutil

            try:
                shutil.rmtree(temp_dir)
            except Exception as exc:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {exc}")


# ------------------------------------------------------------------
# Route: install-from-file
# ------------------------------------------------------------------


@router.post("/install-from-file", response_model=Dict[str, Any])
async def install_from_file(
    fastapi_request: Request,
    file: UploadFile = File(...),
    allow_overwrite: str = Form("false"),
    profile_id: str = Query(
        "default-user", description="User profile ID for role mapping"
    ),
):
    """
    Install capability package from .mindpack file

    Supports offline installation of capability packages.
    Validates manifest, checks conflicts, and installs to capabilities directory.
    """
    if not file.filename.endswith(".mindpack"):
        raise HTTPException(status_code=400, detail="File must be a .mindpack file")

    # Save upload to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mindpack") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        overwrite = allow_overwrite.lower() in ("true", "1", "yes")
        result = await run_install_pipeline(
            fastapi_app=fastapi_request.app,
            mindpack_path=tmp_path,
            allow_overwrite=overwrite,
            source_label="install-from-file",
            extra_metadata={"installed_from_file": True},
        )

        return {
            "success": True,
            "capability_id": result.capability_code,
            "version": result.version,
            "message": f"Successfully installed {result.capability_code} v{result.version}",
            "warnings": result.warnings,
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


class InstallFromCloudRequest(BaseModel):
    """Request model for installing pack from cloud provider"""

    pack_ref: str = Field(
        ..., description="Pack reference in format 'provider_id:code@version'"
    )
    provider_id: str = Field(..., description="Provider ID to download from")
    verify_checksum: bool = Field(True, description="Whether to verify SHA256 checksum")


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
):
    """
    Install capability pack from cloud provider

    Downloads pack from configured cloud provider and installs it locally.
    Supports any provider that implements the CloudProvider interface.
    """
    try:
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
            overwrite = allow_overwrite.lower() in ("true", "1", "yes")
            result = await run_install_pipeline(
                fastapi_app=fastapi_request.app,
                mindpack_path=pack_file,
                allow_overwrite=overwrite,
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
