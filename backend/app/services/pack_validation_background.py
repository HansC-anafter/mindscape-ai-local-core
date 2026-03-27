"""Background pack validation with startup resume support."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from pathlib import Path
from typing import Any, Dict, Optional

import anyio
import yaml

from app.routes.core.admin_reload import CapabilityValidator
from app.services.install_result import InstallResult
from app.services.pack_activation_service import PackActivationService
from app.services.playbook_installer import PlaybookInstaller
from app.services.post_install_modules.playbook_validator import PlaybookValidator
from app.services.restart_webhook import get_restart_webhook_service
from app.services.stores.installed_packs_store import InstalledPacksStore

logger = logging.getLogger(__name__)

_ACTIVE_VALIDATION_TASKS: Dict[str, asyncio.Task[Any]] = {}
_installed_packs_store = InstalledPacksStore()
_pack_activation_service = PackActivationService()


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _resolve_local_core_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_validation_status_payload(
    state: str,
    *,
    mode: str,
    started_at: Optional[str] = None,
    warnings: Optional[list[str]] = None,
    errors: Optional[list[str]] = None,
    playbook_validation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    updated_at = _utc_now_iso()
    payload: Dict[str, Any] = {
        "state": state,
        "mode": mode,
        "updated_at": updated_at,
    }
    if started_at:
        payload["started_at"] = started_at
    if state in {"running", "succeeded", "failed"}:
        payload.setdefault("started_at", started_at or updated_at)
    if state in {"succeeded", "failed"}:
        payload["completed_at"] = updated_at
    if warnings:
        payload["warnings"] = warnings
    if errors:
        payload["errors"] = errors
    if playbook_validation:
        payload["summary"] = {
            "validated": len(playbook_validation.get("validated", []) or []),
            "failed": len(playbook_validation.get("failed", []) or []),
            "skipped": len(playbook_validation.get("skipped", []) or []),
            "warnings": len(playbook_validation.get("warnings", []) or []),
        }
    return payload


def _run_validation_sync(
    *,
    pack_id: str,
    manifest: Dict[str, Any],
    manifest_path: Optional[Path],
    started_at: str,
) -> Dict[str, Any]:
    local_core_root = _resolve_local_core_root()
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    specs_dir = local_core_root / "backend" / "playbooks" / "specs"

    playbook_installer = PlaybookInstaller()
    playbook_installer.capabilities_dir = capabilities_dir
    playbook_installer.specs_dir = specs_dir
    playbook_installer.local_core_root = local_core_root

    validator = PlaybookValidator(
        local_core_root=local_core_root,
        capabilities_dir=capabilities_dir,
        validate_tools_direct_call_func=playbook_installer._validate_tools_direct_call,
    )
    result = InstallResult(capability_code=pack_id)

    _installed_packs_store.update_metadata(
        pack_id,
        {
            "validation": build_validation_status_payload(
                "running",
                mode="background",
                started_at=started_at,
            )
        },
    )
    _pack_activation_service.record_validation_pending(
        pack_id=pack_id,
        manifest=manifest,
        manifest_path=manifest_path,
    )

    validator.validate_installed_playbooks(pack_id, manifest, result)

    if result.errors:
        payload = build_validation_status_payload(
            "failed",
            mode="background",
            started_at=started_at,
            warnings=result.warnings,
            errors=result.errors,
            playbook_validation=result.playbook_validation,
        )
        _installed_packs_store.update_metadata(pack_id, {"validation": payload})
        _pack_activation_service.record_validation_failed(
            pack_id=pack_id,
            manifest=manifest,
            error=result.errors[0],
            manifest_path=manifest_path,
        )
        return {"validation_passed": False, "payload": payload}

    payload = build_validation_status_payload(
        "succeeded",
        mode="background",
        started_at=started_at,
        warnings=result.warnings,
        playbook_validation=result.playbook_validation,
    )
    _installed_packs_store.update_metadata(pack_id, {"validation": payload})
    _pack_activation_service.record_validation_succeeded(
        pack_id=pack_id,
        manifest=manifest,
        manifest_path=manifest_path,
    )
    return {"validation_passed": True, "payload": payload}


async def _run_validation_task(
    *,
    pack_id: str,
    manifest: Dict[str, Any],
    manifest_path: Optional[Path],
    restart_required: bool,
    version: str,
    extra_metadata: Optional[Dict[str, Any]],
) -> None:
    started_at = _utc_now_iso()
    try:
        outcome = await anyio.to_thread.run_sync(
            partial(
                _run_validation_sync,
                pack_id=pack_id,
                manifest=manifest,
                manifest_path=manifest_path,
                started_at=started_at,
            )
        )

        if restart_required:
            webhook_service = get_restart_webhook_service()
            if webhook_service.is_configured():
                cap_validator = CapabilityValidator([Path("/app/backend/app/capabilities")])
                validation = await anyio.to_thread.run_sync(cap_validator.validate_all)
                webhook_kwargs = {
                    "capability_code": pack_id,
                    "validation_passed": outcome["validation_passed"] and validation["valid"],
                    "version": version,
                }
                if extra_metadata:
                    webhook_kwargs["extra_data"] = extra_metadata
                await webhook_service.notify_restart_required(**webhook_kwargs)
    except Exception as exc:
        logger.exception("Background pack validation crashed for %s", pack_id)
        payload = build_validation_status_payload(
            "failed",
            mode="background",
            started_at=started_at,
            errors=[f"Background validation crashed: {exc}"],
        )
        try:
            _installed_packs_store.update_metadata(pack_id, {"validation": payload})
            _pack_activation_service.record_validation_failed(
                pack_id=pack_id,
                manifest=manifest,
                error=str(exc),
                manifest_path=manifest_path,
            )
        except Exception:
            logger.exception(
                "Failed to persist background validation crash state for %s",
                pack_id,
            )
    finally:
        _ACTIVE_VALIDATION_TASKS.pop(pack_id, None)


def schedule_pack_validation(
    *,
    pack_id: str,
    manifest: Dict[str, Any],
    manifest_path: Optional[Path],
    restart_required: bool,
    version: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    existing = _ACTIVE_VALIDATION_TASKS.get(pack_id)
    if existing and not existing.done():
        return False
    task = asyncio.create_task(
        _run_validation_task(
            pack_id=pack_id,
            manifest=manifest,
            manifest_path=manifest_path,
            restart_required=restart_required,
            version=version,
            extra_metadata=extra_metadata,
        )
    )
    _ACTIVE_VALIDATION_TASKS[pack_id] = task
    return True


async def resume_pending_pack_validations() -> None:
    local_core_root = _resolve_local_core_root()
    capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
    for row in _installed_packs_store.list_installed_metadata():
        pack_id = row["pack_id"]
        metadata = row.get("metadata") or {}
        validation = metadata.get("validation") or {}
        if validation.get("state") not in {"pending", "running"}:
            continue

        manifest_path = capabilities_dir / pack_id / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning(
                "Failed to resume pack validation for %s: manifest unreadable (%s)",
                pack_id,
                exc,
            )
            continue

        activation = _pack_activation_service.get_state(pack_id) or {}
        schedule_pack_validation(
            pack_id=pack_id,
            manifest=manifest,
            manifest_path=manifest_path,
            restart_required=activation.get("activation_state") == "pending_restart",
            version=(metadata.get("version") or manifest.get("version") or "1.0.0"),
            extra_metadata=None,
        )
