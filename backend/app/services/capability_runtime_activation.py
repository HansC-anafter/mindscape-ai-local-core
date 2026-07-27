"""Explicit runtime activation for installed capability APIs."""

from __future__ import annotations

import logging
import time
import hashlib
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from sqlalchemy import text

from backend.app.services.capability_runtime_refresh import (
    prepare_capability_for_reactivation,
)
from backend.app.services.capability_pack_route_cache import (
    clear_installed_capability_metadata_caches,
)

logger = logging.getLogger(__name__)


def activate_declared_outcome_adapter(
    *,
    capability_code: str,
    installed_artifact_sha256: str | None = None,
) -> dict[str, Any] | None:
    """Restore one active capability's declared outcome contract."""

    from app.services.capability_registry import get_registry

    capability_entry = get_registry().get_capability(capability_code)
    if not isinstance(capability_entry, dict):
        raise ValueError(f"capability_registry_entry_not_found:{capability_code}")
    manifest = capability_entry.get("manifest") or {}
    if manifest.get("product_outcome_adapter") is None:
        return None
    capability_dir = Path(capability_entry["directory"])
    manifest_path = capability_dir / "manifest.yaml"
    if not manifest_path.exists():
        raise ValueError(f"capability_manifest_not_found:{capability_code}")
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    context = _prepare_outcome_adapter_context(
        capability_entry,
        capability_code=capability_code,
        manifest_sha256=manifest_sha256,
        installed_artifact_sha256=installed_artifact_sha256,
    )
    prepared = _materialize_prepared_outcome_adapter(
        capability_entry,
        capability_code=capability_code,
        manifest_sha256=manifest_sha256,
        context=context,
    )
    return _attach_prepared_outcome_adapter(
        capability_entry,
        prepared,
    )


def restore_active_outcome_adapters(app: FastAPI) -> dict[str, Any]:
    """Restore declared contracts only for capabilities active in this process."""

    from backend.app.services.capability_api_loader import _get_runtime_state

    state = _get_runtime_state(app)
    capability_codes = sorted(state.get("activated_capabilities") or ())
    restored = []
    failed = []
    for capability_code in capability_codes:
        try:
            readback = activate_declared_outcome_adapter(
                capability_code=capability_code,
            )
            if readback is not None:
                restored.append(
                    {
                        "capability_code": capability_code,
                        **readback,
                    }
                )
        except Exception as exc:
            logger.error(
                "Outcome adapter startup restore failed: capability=%s error=%s",
                capability_code,
                type(exc).__name__,
                exc_info=True,
            )
            failed.append(
                {
                    "capability_code": capability_code,
                    "error_code": type(exc).__name__,
                }
            )
    receipt = {
        "state": "failed" if failed else "restored",
        "active_capability_count": len(capability_codes),
        "restored_count": len(restored),
        "failed_count": len(failed),
        "restored": restored,
        "failed": failed,
    }
    app.state.durable_outcome_adapter_restore_receipt = receipt
    return receipt


def activate_installed_capability_routes(
    *,
    app: FastAPI,
    capability_code: str,
    reason: str,
    expected_manifest_hash: str | None = None,
    installed_artifact_sha256: str | None = None,
) -> Dict[str, Any]:
    """Refresh descriptors and activate one installed capability in this process."""

    started = time.monotonic()
    from app.services.capability_registry import get_registry, reload_capability
    from backend.app.services.capability_api_loader import (
        _get_runtime_state,
        activate_capability_api_code,
        refresh_seeded_capability_descriptors,
    )

    state = _get_runtime_state(app)
    with state["activation_lock"]:
        clear_installed_capability_metadata_caches(
            capability_code=capability_code,
            reason=f"explicit_runtime_activation:{reason}",
        )
        descriptors = refresh_seeded_capability_descriptors(app)
        matching_descriptors = [
            descriptor
            for descriptor in descriptors
            if descriptor.capability_code == capability_code
        ]
        capabilities_dir = (
            matching_descriptors[0].capability_dir.parent
            if matching_descriptors
            else None
        )
        if not reload_capability(capability_code, capabilities_dir):
            raise ValueError(f"capability_manifest_not_found:{capability_code}")
        manifest_path = (
            matching_descriptors[0].manifest_path
            if matching_descriptors
            else Path(__file__).resolve().parent.parent
            / "capabilities"
            / capability_code
            / "manifest.yaml"
        )
        if not manifest_path.exists():
            raise ValueError(f"capability_manifest_not_found:{capability_code}")
        actual_manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if expected_manifest_hash and actual_manifest_hash != expected_manifest_hash:
            raise ValueError("candidate_manifest_hash_readback_mismatch")
        registry_entry = get_registry().get_capability(capability_code)
        if not isinstance(registry_entry, dict):
            raise ValueError(f"capability_registry_entry_not_found:{capability_code}")
        outcome_context = _prepare_outcome_adapter_context(
            registry_entry,
            capability_code=capability_code,
            manifest_sha256=actual_manifest_hash,
            installed_artifact_sha256=installed_artifact_sha256,
        )
        refresh = prepare_capability_for_reactivation(
            app=app,
            capability_code=capability_code,
            descriptors=matching_descriptors,
        )
        prepared_outcome = _materialize_prepared_outcome_adapter(
            registry_entry,
            capability_code=capability_code,
            manifest_sha256=actual_manifest_hash,
            context=outcome_context,
        )
        routers = activate_capability_api_code(
            app=app,
            capability_code=capability_code,
            activation_mode=f"explicit_install_activation:{reason}",
            activation_service=None,
            force_refresh=True,
        )
        outcome_snapshot = _attach_prepared_outcome_adapter(
            get_registry().get_capability(capability_code),
            prepared_outcome,
        )
        if routers:
            app.openapi_schema = None
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    if duration_ms >= 1000:
        logger.warning(
            "Capability runtime activation was slow: capability=%s duration_ms=%.2f",
            capability_code,
            duration_ms,
        )
    return {
        "state": "activated",
        "capability_code": capability_code,
        "descriptors": len(matching_descriptors),
        "routers_registered": len(routers),
        "routes_removed": refresh["removed_routes"],
        "modules_purged": refresh["purged_modules"],
        "duration_ms": duration_ms,
        "manifest_hash": actual_manifest_hash,
        "outcome_adapter": outcome_snapshot,
    }


def _prepare_outcome_adapter_context(
    capability_entry: dict[str, Any],
    *,
    capability_code: str,
    manifest_sha256: str,
    installed_artifact_sha256: str | None,
) -> dict[str, Any] | None:
    manifest = capability_entry.get("manifest") or {}
    if manifest.get("product_outcome_adapter") is None:
        return None
    artifact_sha256 = str(
        installed_artifact_sha256 or ""
    ).strip().lower() or _read_committed_artifact_sha256(
        capability_code=capability_code,
        manifest_sha256=manifest_sha256,
    )
    if len(artifact_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in artifact_sha256
    ):
        raise ValueError("outcome_adapter_artifact_sha256_required")
    from backend.app.services.workflow.durable_state.outcome_runtime_trust import (
        OutcomeRuntimeTrust,
    )

    return {
        "artifact_sha256": artifact_sha256,
        "trust": OutcomeRuntimeTrust.from_mounted_files(),
    }


def _materialize_prepared_outcome_adapter(
    capability_entry: dict[str, Any],
    *,
    capability_code: str,
    manifest_sha256: str,
    context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if context is None:
        return None
    from backend.app.services.workflow.durable_state.outcome_adapter_activation import (
        materialize_declared_outcome_adapter,
    )

    manifest = capability_entry.get("manifest") or {}
    isolated_entry = {
        "manifest": manifest,
        "directory": capability_entry.get("directory"),
    }
    snapshot = materialize_declared_outcome_adapter(
        isolated_entry,
        capability_code=capability_code,
        installed_manifest_sha256=manifest_sha256,
        installed_artifact_sha256=context["artifact_sha256"],
        trust=context["trust"],
        runtime_active=True,
    )
    if snapshot is None:
        return None
    return {
        "snapshot": snapshot,
        "artifact_sha256": context["artifact_sha256"],
    }


def _attach_prepared_outcome_adapter(
    capability_entry: dict[str, Any] | None,
    prepared: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if prepared is None:
        return None
    if not isinstance(capability_entry, dict):
        raise ValueError("outcome_adapter_active_registry_entry_missing")
    from backend.app.services.workflow.durable_state.outcome_adapter_resolver import (
        attach_outcome_adapter_snapshot,
    )

    snapshot = attach_outcome_adapter_snapshot(
        capability_entry,
        prepared["snapshot"],
    )
    descriptor = dict(snapshot.descriptor)
    return {
        "state": "materialized",
        "descriptor_id": descriptor["descriptor_id"],
        "descriptor_sha256": descriptor["descriptor_sha256"],
        "descriptor_key_id": descriptor["key_id"],
        "adapter_contract_version": snapshot.export_version,
        "artifact_sha256": prepared["artifact_sha256"],
    }


def _read_committed_artifact_sha256(
    *,
    capability_code: str,
    manifest_sha256: str,
) -> str:
    from backend.app.database.engine import engine_postgres_core

    if engine_postgres_core is None:
        return ""
    with engine_postgres_core.connect() as conn:
        value = conn.execute(
            text(
                """
                SELECT artifact_sha256
                FROM pack_install_commit_receipts
                WHERE pack_id = :pack_id
                  AND manifest_hash = :manifest_hash
                ORDER BY committed_at DESC
                LIMIT 1
                """
            ),
            {
                "pack_id": capability_code,
                "manifest_hash": manifest_sha256,
            },
        ).scalar_one_or_none()
    return str(value or "").strip().lower()
