import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from backend.app.database.write_readiness import (
    DatabaseWriteNotReadyError,
    check_core_write_readiness,
    ensure_core_write_ready,
)
from app.services.pack_activation_service import PackActivationService
from app.services.capability_pack_route_cache import (
    clear_installed_capability_metadata_caches,
)
from app.services.stores.installed_packs_store import InstalledPacksStore
from .paths import (
    OVERWRITE_CONFIRMATION_PHRASE,
    OVERWRITE_REVIEW_CONFIRMATION_PHRASE,
    _build_dirty_overwrite_detail,
    _ensure_sys_path,
    _handle_dev_mode_reload_trigger,
    _resolve_local_core_root,
    _utc_now,
)
from .pipeline_followup import run_post_install_followups
from .registry_sync import (
    _defer_restart_webhook_if_blocked,
    _sync_install_time_registries,
)
from .restart_policy import (
    apply_restart_decision_to_payload,
    build_install_restart_decision,
)
from .schemas import InstallPipelineResult

logger = logging.getLogger(__name__)
installed_packs_store = InstalledPacksStore()
pack_activation_service = PackActivationService()


async def _reload_capability_registry_modules() -> None:
    """Reload both supported capability registry module identities."""
    from app.services.capability_registry import load_capabilities as load_app_capabilities

    await run_in_threadpool(load_app_capabilities, reset=True)

    try:
        from backend.app.services.capability_registry import (
            load_capabilities as load_backend_capabilities,
        )
    except Exception:
        return

    if load_backend_capabilities is not load_app_capabilities:
        await run_in_threadpool(load_backend_capabilities, reset=True)


async def run_install_pipeline(
    *,
    fastapi_app,
    mindpack_path: Path,
    allow_overwrite: bool,
    overwrite_review_confirmation: str,
    source_label: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> InstallPipelineResult:
    _ensure_sys_path()
    ensure_core_write_ready(operation=f"capability_pack_install:{source_label}")

    from app.services.mindpack_extractor import MindpackExtractor
    from app.services.manifest_validator import ManifestValidator
    from app.services.playbook_installer import PlaybookInstaller
    from app.services.runtime_assets_installer import RuntimeAssetsInstaller
    from app.services.post_install import PostInstallHandler
    from app.services.install_result import InstallResult
    from backend.app.services.model_route_slot_registry import (
        ModelRouteSlotRegistry,
    )

    local_core_root = _resolve_local_core_root()
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    specs_dir = local_core_root / "backend" / "playbooks" / "specs"
    i18n_base_dir = local_core_root / "backend" / "i18n" / "playbooks"

    pipeline = InstallPipelineResult()

    # 1. Extract mindpack
    extractor = MindpackExtractor(local_core_root)
    extract_ok, temp_dir, capability_code, cap_dir = await run_in_threadpool(
        extractor.extract,
        mindpack_path,
    )

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
        is_valid, validation_errors, validation_warnings = await run_in_threadpool(
            validator.validate,
            manifest_path,
            cap_dir,
            skip_validation=skip_validation,
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
                from app.services.install_integrity import (
                    build_dirty_review_payload,
                    check_dirty_state,
                )

                dirty = await run_in_threadpool(check_dirty_state, existing_cap_dir)
                if dirty.is_dirty:
                    review_payload = await run_in_threadpool(
                        build_dirty_review_payload,
                        existing_cap_dir,
                        cap_dir,
                        dirty,
                    )
                    if not allow_overwrite:
                        raise HTTPException(
                            status_code=409,
                            detail=_build_dirty_overwrite_detail(
                                dirty=dirty,
                                incoming_version=pipeline.version,
                                review_payload=review_payload,
                                error="local_modifications_detected",
                                message=(
                                    f"{capability_code}: {len(dirty.modified)} modified, "
                                    f"{len(dirty.added)} added, {len(dirty.deleted)} deleted "
                                    f"since v{dirty.installed_version} install"
                                ),
                                hint=(
                                    "Review the per-file diffs first. Only if every local change "
                                    "is already reflected in cloud source, resubmit with "
                                    "allow_overwrite=true, "
                                    f"overwrite_confirmation={OVERWRITE_CONFIRMATION_PHRASE}, and "
                                    "overwrite_review_confirmation="
                                    f"{OVERWRITE_REVIEW_CONFIRMATION_PHRASE}."
                                ),
                            ),
                        )
                    if (
                        str(overwrite_review_confirmation or "").strip()
                        != OVERWRITE_REVIEW_CONFIRMATION_PHRASE
                    ):
                        raise HTTPException(
                            status_code=409,
                            detail=_build_dirty_overwrite_detail(
                                dirty=dirty,
                                incoming_version=pipeline.version,
                                review_payload=review_payload,
                                error="overwrite_review_confirmation_required",
                                message=(
                                    "Force overwrite is blocked until local modification diffs "
                                    "are reviewed."
                                ),
                                hint=(
                                    "Inspect each diff item. If the incoming pack does not omit "
                                    "required local-core fixes, resubmit with "
                                    "allow_overwrite=true, "
                                    f"overwrite_confirmation={OVERWRITE_CONFIRMATION_PHRASE}, and "
                                    "overwrite_review_confirmation="
                                    f"{OVERWRITE_REVIEW_CONFIRMATION_PHRASE}."
                                ),
                            ),
                        )
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
        await run_in_threadpool(
            playbook_installer._install_playbooks,
            cap_dir,
            capability_code,
            manifest,
            result,
        )

        runtime_installer = RuntimeAssetsInstaller(
            local_core_root=local_core_root, capabilities_dir=capabilities_dir
        )
        await run_in_threadpool(
            runtime_installer.install_all,
            cap_dir,
            capability_code,
            manifest,
            result,
            temp_dir,
        )

        # Migrations
        await run_in_threadpool(
            runtime_installer.execute_migrations,
            capability_code,
            result,
        )
        if hasattr(result, "migration_status") and result.migration_status:
            mig = result.migration_status.get(capability_code)
            if mig == "waiting_db":
                raise DatabaseWriteNotReadyError(
                    check_core_write_readiness(
                        operation=f"capability_pack_migration:{capability_code}"
                    )
                )
            if mig in ("failed", "error"):
                result.add_error(
                    f"Migration execution failed for {capability_code}: {mig}"
                )
            elif mig == "applied":
                logger.info(f"Successfully executed migrations for {capability_code}")
        else:
            logger.warning(f"Migration status not available for {capability_code}")

        # Post-install hooks required for pack readiness. Playbook validation
        # runs as a resumable background task so install responses do not block
        # on every validation subprocess.
        post_handler = PostInstallHandler(
            local_core_root=local_core_root,
            capabilities_dir=capabilities_dir,
            specs_dir=specs_dir,
            validate_tools_direct_call_func=playbook_installer._validate_tools_direct_call,
        )
        await run_in_threadpool(
            post_handler.run_required_tasks,
            cap_dir,
            capability_code,
            manifest,
            result,
        )

        registry_sync_state = await run_in_threadpool(
            _sync_install_time_registries,
            local_core_root=local_core_root,
            capability_code=capability_code,
            manifest=manifest,
            result=result,
        )
        contract_lane_changed = registry_sync_state.contract_lane_changed

        # 4. Reload capability registry
        hot_reload_performed = False
        activation_error: Optional[str] = None
        try:
            from app.services.capability_registry import get_registry, load_capabilities
            from app.services.capability_reload_manager import (
                hot_reload_enabled,
                reload_capability_routes,
            )

            registry = get_registry()
            if hasattr(registry, "_capabilities_cache"):
                registry._capabilities_cache.clear()
            if hasattr(registry, "_tools_cache"):
                registry._tools_cache.clear()

            if contract_lane_changed:
                await _reload_capability_registry_modules()
                result.add_warning(
                    "Contract import paths changed; skipping in-process hot reload and requiring a backend restart."
                )
                logger.info(
                    "Skipped in-process hot reload for %s because contract import paths changed",
                    capability_code,
                )
            elif hot_reload_enabled():
                pipeline.hot_reload_result = await run_in_threadpool(
                    reload_capability_routes,
                    fastapi_app,
                    f"{source_label}:{capability_code}",
                )
                hot_reload_performed = True
                logger.info(f"Hot reload completed for {capability_code}")
            else:
                await _reload_capability_registry_modules()
                logger.info(f"Reloaded capability registry for {capability_code}")
        except Exception as exc:
            activation_error = f"Failed to reload capability registry/routes: {exc}"
            logger.warning(f"Failed to reload capability registry/routes: {exc}")
            result.add_warning(activation_error)
            try:
                await _reload_capability_registry_modules()
            except Exception:
                pass

        # 5. Restart decision
        restart_decision = build_install_restart_decision(
            contract_lane_changed=contract_lane_changed,
            hot_reload_performed=hot_reload_performed,
        )
        pipeline.restart_decision = restart_decision.to_payload()
        pipeline.restart_required = restart_decision.legacy_restart_required
        env = os.getenv("ENVIRONMENT", "development")

        if pipeline.restart_required and env in ("development", "dev"):
            _handle_dev_mode_reload_trigger(
                pipeline=pipeline,
                result=result,
                capability_code=capability_code,
                env=env,
            )
            restart_decision = build_install_restart_decision(
                contract_lane_changed=contract_lane_changed,
                backend_restart_triggered=pipeline.restart_triggered,
                hot_reload_performed=hot_reload_performed,
            )
            pipeline.restart_decision = restart_decision.to_payload()
            pipeline.restart_required = restart_decision.legacy_restart_required
        _defer_restart_webhook_if_blocked(
            pipeline=pipeline,
            result=result,
            capability_code=capability_code,
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
        pack_metadata = apply_restart_decision_to_payload(
            pack_metadata,
            pipeline.restart_decision,
        )

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
            route_slots = ModelRouteSlotRegistry().extract_pack_slots_from_manifest(
                pack_id=capability_code,
                pack_meta=manifest,
                manifest_path=(
                    str(installed_manifest_path)
                    if installed_manifest_path.exists()
                    else str(manifest_path)
                ),
                installed=True,
                enabled=True,
            )
            pack_metadata["model_route_slots"] = route_slots
            pack_metadata["model_route_slot_count"] = len(route_slots)
        except Exception as exc:
            logger.warning(
                "Failed to register model route slots for %s: %s",
                capability_code,
                exc,
            )
            result.add_warning(f"Failed to register model route slots: {exc}")

        validation_state = None
        if manifest.get("playbooks"):
            from app.services.pack_validation_background import (
                build_validation_status_payload,
            )

            validation_state = build_validation_status_payload(
                "pending",
                mode="background",
            )
            pack_metadata["validation"] = validation_state

        try:
            await run_in_threadpool(
                installed_packs_store.upsert_pack,
                pack_id=capability_code,
                installed_at=_utc_now(),
                enabled=True,
                metadata=pack_metadata,
            )
        except Exception as exc:
            logger.warning(f"Failed to register pack in database: {exc}")
            result.add_warning(f"Failed to register pack in database: {exc}")

        clear_installed_capability_metadata_caches(
            capability_code=capability_code,
            reason="install_pipeline_registered",
        )

        try:
            pipeline.activation = await run_in_threadpool(
                pack_activation_service.record_install_outcome,
                pack_id=capability_code,
                manifest=manifest,
                install_result=result,
                enabled=True,
                hot_reload_performed=hot_reload_performed,
                restart_required=pipeline.restart_required,
                restart_decision=pipeline.restart_decision,
                manifest_path=installed_manifest_path
                if installed_manifest_path.exists()
                else None,
                activation_error=activation_error,
            )
            if validation_state is not None:
                pipeline.activation = await run_in_threadpool(
                    pack_activation_service.record_validation_pending,
                    pack_id=capability_code,
                    manifest=manifest,
                    manifest_path=installed_manifest_path
                    if installed_manifest_path.exists()
                    else None,
                )
        except Exception as exc:
            logger.warning("Failed to persist pack activation state: %s", exc)
            result.add_warning(f"Failed to persist pack activation state: {exc}")

        pipeline.pack_metadata = pack_metadata
        pipeline.validation = validation_state
        await run_post_install_followups(
            pipeline=pipeline,
            result=result,
            capability_code=capability_code,
            manifest=manifest,
            installed_manifest_path=installed_manifest_path,
            installed_cap_dir=target_dir,
            pack_metadata=pack_metadata,
            validation_state=validation_state,
            extra_metadata=extra_metadata,
        )

        pipeline.success = True
        pipeline.warnings = result.warnings
        return pipeline

    finally:
        if temp_dir and temp_dir.exists():
            import shutil

            try:
                shutil.rmtree(temp_dir)
            except Exception as exc:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {exc}")


# ------------------------------------------------------------------
# Route: install-from-file
# ------------------------------------------------------------------
