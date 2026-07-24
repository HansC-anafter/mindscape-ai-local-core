import logging
import os
import uuid
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
from .paths import (
    OVERWRITE_REVIEW_CONFIRMATION_PHRASE,
    _ensure_sys_path,
    _handle_dev_mode_reload_trigger,
    _resolve_local_core_root,
)
from .install_commit_core.dirty_state import validate_existing_install_dirty_state
from .install_commit_coordinator import InstallCommitCoordinator
from .install_commit_core.candidate_metadata import build_candidate_metadata
from .install_commit_core.requirement_preflight import (
    validate_atomic_install_requirements,
)
from .pipeline_followup import run_post_install_followups
from .pipeline_registry_reload import reload_capability_registry_modules
from .registry_sync import (
    _defer_restart_webhook_if_blocked,
    _preview_install_time_registries,
)
from .restart_policy import (
    build_install_restart_decision,
)
from .schemas import InstallPipelineResult
from backend.app.services.pack_install_version_preflight import (
    validate_existing_pack_version_truth,
)

logger = logging.getLogger(__name__)


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
    from app.services.install_result import InstallResult
    local_core_root = _resolve_local_core_root()
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    specs_dir = local_core_root / "backend" / "playbooks" / "specs"
    i18n_base_dir = local_core_root / "backend" / "i18n" / "playbooks"

    pipeline = InstallPipelineResult()
    commit_coordinator: Optional[InstallCommitCoordinator] = None

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

        existing_cap_dir = capabilities_dir / capability_code
        await validate_existing_install_dirty_state(
            existing_cap_dir=existing_cap_dir,
            candidate_cap_dir=cap_dir,
            capability_code=capability_code,
            incoming_version=pipeline.version,
            allow_overwrite=allow_overwrite,
            overwrite_review_confirmation=overwrite_review_confirmation,
            run_in_threadpool_func=run_in_threadpool,
        )
        if existing_cap_dir.exists():
            await run_in_threadpool(
                validate_existing_pack_version_truth,
                capability_code=capability_code,
                candidate_manifest_path=manifest_path,
                live_manifest_path=existing_cap_dir / "manifest.yaml",
                artifact_sha256=str(
                    (extra_metadata or {}).get("archive_sha256") or ""
                )
                or None,
                backout=(extra_metadata or {}).get("backout_receipt"),
                reviewed_split_truth_repair=(
                    allow_overwrite
                    and overwrite_review_confirmation
                    == OVERWRITE_REVIEW_CONFIRMATION_PHRASE
                ),
            )

        requirement_blockers = await run_in_threadpool(
            validate_atomic_install_requirements,
            local_core_root=local_core_root,
            candidate_dir=cap_dir,
            manifest=manifest,
        )
        if requirement_blockers:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "pack_atomic_requirement_preflight_failed",
                    "blockers": requirement_blockers,
                },
            )

        # 3. Install playbooks + runtime
        result = InstallResult(capability_code=capability_code)
        result.warnings.extend(validation_warnings)

        runtime_installer = RuntimeAssetsInstaller(
            local_core_root=local_core_root, capabilities_dir=capabilities_dir
        )
        install_id = str((extra_metadata or {}).get("install_id") or uuid.uuid4().hex)
        commit_coordinator = InstallCommitCoordinator(
            install_id=install_id,
            capability_code=capability_code,
            runtime_installer=runtime_installer,
        )
        prepared = await run_in_threadpool(
            commit_coordinator.prepare,
            cap_dir=cap_dir,
            manifest=manifest,
            result=result,
            temp_dir=temp_dir,
        )

        # Validate and materialize playbooks only inside the retained candidate.
        # Global legacy paths are non-authoritative and must never be mutated
        # before the single install truth commit.
        playbook_installer = PlaybookInstaller()
        playbook_installer.capabilities_dir = prepared.staging_cap_dir.parent
        playbook_installer.specs_dir = specs_dir
        playbook_installer.i18n_base_dir = i18n_base_dir
        playbook_installer.local_core_root = local_core_root
        await run_in_threadpool(
            playbook_installer._install_playbooks,
            cap_dir,
            capability_code,
            manifest,
            result,
            write_legacy_compatibility=False,
        )

        await run_in_threadpool(
            commit_coordinator.execute_candidate_migrations,
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
            if mig in ("failed", "error", "waiting_db_incident"):
                result.add_error(
                    f"Migration execution failed for {capability_code}: {mig}"
                )
            elif mig == "applied":
                logger.info(f"Successfully executed migrations for {capability_code}")
        else:
            logger.warning(f"Migration status not available for {capability_code}")
        if result.has_errors():
            raise HTTPException(
                status_code=400,
                detail=result.errors[0],
            )
        await run_in_threadpool(commit_coordinator.publish)

        registry_sync_state = await run_in_threadpool(
            _preview_install_time_registries,
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
            from app.services.capability_registry import get_registry

            registry = get_registry()
            if hasattr(registry, "_capabilities_cache"):
                registry._capabilities_cache.clear()
            if hasattr(registry, "_tools_cache"):
                registry._tools_cache.clear()

            await reload_capability_registry_modules(
                capability_code=capability_code,
                run_in_threadpool_func=run_in_threadpool,
            )
            if contract_lane_changed:
                result.add_warning(
                    "Contract import paths changed; the targeted registry metadata is refreshed and a backend restart is required."
                )
                logger.info(
                    "Refreshed registry metadata for %s; contract imports require restart",
                    capability_code,
                )
            else:
                hot_reload_performed = True
                pipeline.hot_reload_result = {
                    "enabled": True,
                    "mode": "targeted_registry_reload",
                    "capability_code": capability_code,
                }
                logger.info("Reloaded capability registry slice for %s", capability_code)
        except Exception as exc:
            activation_error = f"Failed to reload capability registry/routes: {exc}"
            logger.warning(f"Failed to reload capability registry/routes: {exc}")
            result.add_warning(activation_error)

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
        installed_manifest_path = target_dir / "manifest.yaml"
        pack_metadata, validation_state = await run_in_threadpool(
            build_candidate_metadata,
            capability_code=capability_code,
            version=str(pipeline.version),
            manifest=manifest,
            installed_manifest_path=installed_manifest_path,
            restart_decision=pipeline.restart_decision,
            extra_metadata=extra_metadata,
        )
        from app.services.pack_activation_service import PackActivationService

        activation_record = PackActivationService(store=object()).build_install_record(
            pack_id=capability_code,
            manifest=manifest,
            install_result=result,
            enabled=True,
            hot_reload_performed=hot_reload_performed,
            restart_required=pipeline.restart_required,
            restart_decision=pipeline.restart_decision,
            manifest_path=installed_manifest_path,
            activation_error=activation_error,
        )
        pipeline.activation_candidate = activation_record.to_receipt_payload()
        pipeline.activation = {
            **pipeline.activation_candidate,
            "commit_state": "candidate_pending_execution_activation",
        }

        pipeline.pack_metadata = pack_metadata
        pipeline.pack_metadata["install_projection_manifest"] = {
            key: manifest.get(key, [])
            for key in (
                "contract_exports",
                "object_exports",
                "object_resolvers",
                "meeting_projections",
                "materializers",
                "graph_projections",
                "affordances",
            )
        }
        pipeline.validation = validation_state
        pipeline.migration_receipts = dict(result.migration_receipts)
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
        pipeline.install_commit_coordinator = commit_coordinator
        pipeline.install_commit_receipt = commit_coordinator.receipt()
        return pipeline

    except Exception:
        if commit_coordinator is not None:
            was_published = bool(
                commit_coordinator.prepared
                and commit_coordinator.prepared.published
            )
            await run_in_threadpool(commit_coordinator.restore_previous)
            if was_published:
                try:
                    await reload_capability_registry_modules(
                        capability_code=capability_code,
                        run_in_threadpool_func=run_in_threadpool,
                    )
                except Exception:
                    logger.exception(
                        "Failed to reload previous capability after candidate restore: %s",
                        capability_code,
                    )
        raise
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
