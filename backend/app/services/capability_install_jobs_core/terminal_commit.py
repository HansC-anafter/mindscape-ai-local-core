"""Terminal capability install commit and candidate restoration."""

from __future__ import annotations

import logging
import hashlib
from typing import Any, Mapping

import yaml

from backend.app.services.capability_install_job_payloads import (
    _pipeline_result_to_payload,
)
from backend.app.services.capability_pack_route_cache import (
    clear_installed_capability_metadata_caches,
)
from backend.app.services.pack_install_truth_committer import PackInstallTruthCommitter
from backend.app.services.pack_install_reconciliation import (
    PackInstallReconciliationStore,
    record_filesystem_cleanup_result,
    record_projection_result,
)

logger = logging.getLogger(__name__)


class _ProjectionCommitResult:
    def add_error(self, message: str) -> None:
        raise RuntimeError(message)


def _coordinator(result: Any):
    coordinator = getattr(result, "install_commit_coordinator", None)
    if coordinator is None:
        raise RuntimeError("install_commit_coordinator_missing")
    return coordinator


def restore_previous_candidate(result: Any) -> dict[str, Any]:
    """Restore previous files and reload their registry projection."""

    coordinator = _coordinator(result)
    coordinator.restore_previous()
    from backend.app.services.capability_registry import reload_capability

    if coordinator.prepared and coordinator.prepared.target_cap_dir.exists():
        if not reload_capability(coordinator.capability_code):
            raise RuntimeError("previous_capability_registry_reload_failed")
        manifest_path = coordinator.prepared.target_cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            raise RuntimeError("previous_capability_manifest_missing")
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return {
            "capability_code": coordinator.capability_code,
            "version": str(manifest.get("version") or ""),
            "manifest_hash": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
    return {
        "capability_code": coordinator.capability_code,
        "version": None,
        "manifest_hash": None,
    }


def commit_succeeded_install(
    *,
    service: Any,
    job: Mapping[str, Any],
    result: Any,
    payload: dict[str, Any],
    execution_activation: Mapping[str, Any],
) -> dict[str, Any]:
    """Commit all durable truth, then delete the retained previous tree."""

    coordinator = _coordinator(result)
    coordinator.mark_activated()
    activation_candidate = dict(getattr(result, "activation_candidate", {}) or {})
    manifest_hash = str(activation_candidate.get("manifest_hash") or "")
    if not manifest_hash:
        raise RuntimeError("candidate_manifest_hash_missing")
    payload["install_commit_receipt"] = coordinator.receipt()
    payload["execution_activation"] = dict(execution_activation)
    payload["activation"] = {
        **activation_candidate,
        "install_state": "installed",
        "activation_state": "active",
        "commit_state": "committed",
    }
    source_payload = dict(job.get("source_payload") or {})
    migration_receipt = dict(
        (payload.get("migration_receipts") or {}).get(
            str(payload["capability_code"]),
            {},
        )
    )
    migration_receipt.update(
        {
            "state": activation_candidate.get("migration_state") or "applied",
            "install_commit_state": coordinator.state.value,
        }
    )
    committer = PackInstallTruthCommitter(
        db_role=getattr(service.store, "db_role", "core")
    )
    receipt = committer.commit(
        install_id=str(job["install_id"]),
        pack_id=str(payload["capability_code"]),
        version=str(payload["version"]),
        manifest_hash=manifest_hash,
        artifact_sha256=source_payload.get("archive_sha256"),
        migration_receipt=migration_receipt,
        commit_metadata=dict(payload.get("pack_metadata") or {}),
        activation=activation_candidate,
        result_payload=payload,
    )
    coordinator.mark_committed()
    projection_manifest = dict(
        (payload.get("pack_metadata") or {}).get("install_projection_manifest") or {}
    )
    projection_succeeded = False
    projection_error = None
    try:
        from backend.app.routes.core.capability_install_core.registry_sync import (
            _sync_install_time_registries,
        )

        _sync_install_time_registries(
            local_core_root=coordinator.runtime_installer.local_core_root,
            capability_code=str(payload["capability_code"]),
            manifest=projection_manifest,
            result=_ProjectionCommitResult(),
        )
        projection_succeeded = True
    except Exception as exc:
        projection_error = f"{type(exc).__name__}:{str(exc)[:420]}"
        coordinator.mark_cleanup_pending(exc)
        logger.exception(
            "Committed pack registry projection requires reconciliation: install_id=%s",
            job["install_id"],
        )
    try:
        record_projection_result(
            str(job["install_id"]),
            succeeded=projection_succeeded,
            error=projection_error,
        )
    except Exception:
        # The receipt defaults to pending, so a worker restart still retries.
        logger.exception(
            "Capability install projection receipt update failed: install_id=%s",
            job["install_id"],
        )
    if projection_succeeded:
        cleanup_succeeded = False
        cleanup_error = None
        try:
            coordinator.finalize()
            cleanup_succeeded = True
        except Exception as exc:
            # Retained previous files are cleanup state after durable truth commits.
            # Restoring them here would create split truth between DB and runtime.
            cleanup_error = f"{type(exc).__name__}:{str(exc)[:420]}"
            coordinator.mark_cleanup_pending(exc)
            logger.exception(
                "Capability install committed with retained-tree cleanup pending: install_id=%s",
                job["install_id"],
            )
        try:
            record_filesystem_cleanup_result(
                str(job["install_id"]),
                succeeded=cleanup_succeeded,
                error=cleanup_error,
            )
        except Exception:
            logger.exception(
                "Capability install cleanup receipt update failed: install_id=%s",
                job["install_id"],
            )
    try:
        clear_installed_capability_metadata_caches(
            capability_code=str(payload["capability_code"]),
            reason="install_truth_committed",
        )
    except Exception:
        logger.exception(
            "Capability install cache cleanup failed after truth commit: install_id=%s",
            job["install_id"],
        )
    committed = service.store.get_job(str(job["install_id"]))
    if committed is None:
        raise RuntimeError("committed_install_job_readback_missing")
    committed["commit_receipt"] = receipt
    committed["install_commit_receipt"] = coordinator.receipt()
    try:
        committed["commit_reconciliation"] = PackInstallReconciliationStore(
            db_role=getattr(service.store, "db_role", "core")
        ).get(str(job["install_id"]))
    except Exception:
        logger.exception(
            "Capability install reconciliation readback failed: install_id=%s",
            job["install_id"],
        )
    return committed


def pipeline_payload(result: Any) -> dict[str, Any]:
    return _pipeline_result_to_payload(result)
