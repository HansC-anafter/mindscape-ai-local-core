import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.restart_safety import (
    format_restart_blocker_detail,
    inspect_restart_blockers,
)

from .schemas import InstallPipelineResult, InstallRegistrySyncState

logger = logging.getLogger(__name__)


def _set_validation_followup_result(
    pipeline: InstallPipelineResult,
    *,
    reason: str,
) -> None:
    if pipeline.restart_required and pipeline.webhook_result is None:
        pipeline.webhook_result = {"sent": False, "reason": reason}


def _should_run_restart_webhook(pipeline: InstallPipelineResult) -> bool:
    return bool(pipeline.restart_required and pipeline.webhook_result is None)


def _defer_restart_webhook_if_blocked(
    *,
    pipeline: InstallPipelineResult,
    result: Any,
    capability_code: str,
) -> bool:
    """Prevent restart webhooks from killing active meeting/runtime work."""
    if not pipeline.restart_required or pipeline.webhook_result is not None:
        return False

    blockers = inspect_restart_blockers()
    if not blockers.get("blocked"):
        return False

    detail = format_restart_blocker_detail(blockers)
    reason = blockers.get("reason") or "restart_blocked"
    result.add_warning(
        f"Deferred backend restart webhook for {capability_code}: active or unknown workloads are present ({detail})."
    )
    pipeline.webhook_result = {
        "sent": False,
        "reason": reason,
        "detail": detail,
    }
    logger.info(
        "Deferred restart webhook for %s because restart blockers are present: %s",
        capability_code,
        detail,
    )
    return True


def _sync_install_time_registries(
    *,
    local_core_root: Path,
    capability_code: str,
    manifest: Dict[str, Any],
    result: Any,
) -> InstallRegistrySyncState:
    state = InstallRegistrySyncState()

    try:
        from app.services.runtime_contract_registry import RuntimeContractRegistry

        contract_sync = RuntimeContractRegistry(local_core_root).sync_pack_contracts(
            capability_code,
            manifest,
        )
        state.contract_lane_changed = contract_sync.requires_restart
        if contract_sync.alias_modules:
            logger.info(
                "Synced runtime contract aliases for %s: %s",
                capability_code,
                ", ".join(contract_sync.alias_modules),
            )
    except Exception as exc:
        result.add_error(f"Failed to sync runtime contract registry: {exc}")

    try:
        from app.services.object_catalog_registry import ObjectCatalogRegistry

        object_sync = ObjectCatalogRegistry(local_core_root).sync_pack_objects(
            capability_code,
            manifest,
        )
        state.object_catalog_changed = object_sync.changed
        logger.info(
            "Synced runtime object catalog for %s (%s objects)",
            capability_code,
            object_sync.object_count,
        )
    except Exception as exc:
        result.add_error(f"Failed to sync runtime object catalog registry: {exc}")

    return state


def _schedule_pack_validation_on_current_loop(
    *,
    pack_id: str,
    manifest: Dict[str, Any],
    manifest_path: Optional[Path],
    restart_required: bool,
    version: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    from app.services.pack_validation_background import schedule_pack_validation

    return schedule_pack_validation(
        pack_id=pack_id,
        manifest=manifest,
        manifest_path=manifest_path,
        restart_required=restart_required,
        version=version,
        extra_metadata=extra_metadata,
    )
