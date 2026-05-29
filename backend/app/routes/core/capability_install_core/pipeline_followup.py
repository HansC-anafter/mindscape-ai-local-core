import logging
from pathlib import Path
from typing import Any, Dict, Optional

from starlette.concurrency import run_in_threadpool

from app.services.pack_activation_service import PackActivationService
from app.services.restart_webhook import get_restart_webhook_service
from app.services.stores.installed_packs_store import InstalledPacksStore
from app.services.tool_rag_refresh import refresh_tool_rag_corpus

from .registry_sync import (
    _schedule_pack_validation_on_current_loop,
    _set_validation_followup_result,
    _should_run_restart_webhook,
)
from .schemas import InstallPipelineResult

logger = logging.getLogger(__name__)
installed_packs_store = InstalledPacksStore()
pack_activation_service = PackActivationService()


async def run_post_install_followups(
    *,
    pipeline: InstallPipelineResult,
    result: Any,
    capability_code: str,
    manifest: Dict[str, Any],
    installed_manifest_path: Path,
    installed_cap_dir: Path,
    pack_metadata: Dict[str, Any],
    validation_state: Optional[Dict[str, Any]],
    extra_metadata: Optional[Dict[str, Any]],
) -> None:
    # Refresh tool embeddings in the background after the install copy is published.
    import asyncio as _asyncio

    try:
        async def _bg_reindex():
            try:
                _, indexed_count, mode = await refresh_tool_rag_corpus(
                    log_prefix="Tool RAG install refresh"
                )
                logger.info(
                    "Tool RAG re-indexed after install: %d tools (mode=%s)",
                    indexed_count,
                    mode,
                )
                try:
                    pack_activation_service.record_embedding_succeeded(
                        pack_id=capability_code,
                        manifest=manifest,
                        manifest_path=installed_manifest_path
                        if installed_manifest_path.exists()
                        else None,
                    )
                except Exception as _state_exc:
                    logger.warning(
                        "Failed to persist embedding success state for %s: %s",
                        capability_code,
                        _state_exc,
                    )
                # Invalidate process-level cache so next turn gets fresh results
                try:
                    from backend.app.services.tool_rag import (
                        invalidate_tool_rag_cache,
                    )

                    invalidate_tool_rag_cache()
                except Exception:
                    pass
            except Exception as _exc:
                logger.warning("Tool RAG indexing failed (non-fatal): %s", _exc)
                try:
                    pack_activation_service.record_embedding_failed(
                        pack_id=capability_code,
                        manifest=manifest,
                        error=str(_exc),
                        manifest_path=installed_manifest_path
                        if installed_manifest_path.exists()
                        else None,
                    )
                except Exception as _state_exc:
                    logger.warning(
                        "Failed to persist embedding failure state for %s: %s",
                        capability_code,
                        _state_exc,
                    )

        _asyncio.create_task(_bg_reindex())
    except Exception as exc:
        logger.warning("Tool RAG background task setup failed: %s", exc)

    pipeline.pack_metadata = pack_metadata
    pipeline.validation = validation_state

    # 7. Validation / webhook background follow-up
    if validation_state is not None:
        try:
            scheduled = _schedule_pack_validation_on_current_loop(
                pack_id=capability_code,
                manifest=manifest,
                manifest_path=installed_manifest_path
                if installed_manifest_path.exists()
                else None,
                restart_required=bool(
                    pipeline.restart_required
                    and pipeline.webhook_result is None
                ),
                version=pack_metadata.get("version", "1.0.0"),
                extra_metadata=extra_metadata,
            )
            if scheduled:
                result.add_warning(
                    f"Playbook validation scheduled in background for {capability_code}."
                )
                _set_validation_followup_result(
                    pipeline,
                    reason="scheduled_background_validation",
                )
            else:
                result.add_warning(
                    f"Playbook validation already running in background for {capability_code}."
                )
                _set_validation_followup_result(
                    pipeline,
                    reason="background_validation_already_running",
                )
        except Exception as exc:
            logger.warning(
                "Failed to schedule background playbook validation for %s: %s",
                capability_code,
                exc,
            )
            from app.services.pack_validation_background import (
                build_validation_status_payload,
            )

            failure_state = build_validation_status_payload(
                "failed",
                mode="background",
                errors=[f"Failed to schedule background playbook validation: {exc}"],
            )
            try:
                await run_in_threadpool(
                    installed_packs_store.update_metadata,
                    capability_code,
                    {"validation": failure_state},
                )
                pipeline.activation = await run_in_threadpool(
                    pack_activation_service.record_validation_failed,
                    pack_id=capability_code,
                    manifest=manifest,
                    error=f"Failed to schedule background playbook validation: {exc}",
                    manifest_path=installed_manifest_path
                    if installed_manifest_path.exists()
                    else None,
                )
                pipeline.validation = failure_state
            except Exception as state_exc:
                logger.warning(
                    "Failed to persist schedule failure state for %s: %s",
                    capability_code,
                    state_exc,
                )
            result.add_warning(
                f"Failed to schedule background playbook validation: {exc}"
            )
            _set_validation_followup_result(
                pipeline,
                reason="validation_schedule_failed",
            )

    if _should_run_restart_webhook(pipeline):
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

        if installed_cap_dir.exists():
            hashes = await run_in_threadpool(
                compute_dir_hashes,
                installed_cap_dir,
            )
            await run_in_threadpool(
                save_install_manifest,
                installed_cap_dir,
                pack_metadata.get("version", "1.0.0"),
                hashes,
            )
    except Exception as exc:
        logger.warning(f"Failed to record install hashes: {exc}")
