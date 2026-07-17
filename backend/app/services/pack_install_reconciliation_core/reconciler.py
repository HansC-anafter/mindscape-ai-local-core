"""Reconcile non-authoritative projections after durable pack truth commits."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from backend.app.routes.core.capability_install_core.paths import (
    _resolve_local_core_root,
)
from backend.app.routes.core.capability_install_core.registry_sync import (
    _sync_install_time_registries,
)
from backend.app.services.runtime_database_incident_gate import (
    require_runtime_database_mutation_allowed,
)

from .filesystem import finalize_committed_filesystem
from .store import PackInstallReconciliationStore


class _ProjectionResult:
    def add_error(self, message: str) -> None:
        raise RuntimeError(message)


class CommittedInstallReconciler:
    """Retry one oldest committed install without changing authoritative truth."""

    def __init__(
        self,
        store: Optional[PackInstallReconciliationStore] = None,
        local_core_root: Optional[Path] = None,
    ):
        self.store = store or PackInstallReconciliationStore()
        self.local_core_root = (local_core_root or _resolve_local_core_root()).resolve()

    def has_incomplete(self) -> bool:
        return self.store.has_incomplete()

    def reconcile_next(self) -> Optional[dict[str, Any]]:
        require_runtime_database_mutation_allowed("pack_install_reconciliation_poll")
        row = self.store.next_due()
        if row is None:
            return None
        install_id = str(row["install_id"])
        payload = dict(row.get("result_payload") or {})
        pack_id = str(row.get("pack_id") or "")
        manifest_hash = str(row.get("manifest_hash") or "")
        commit_receipt = dict(payload.get("commit_receipt") or {})
        if (
            str(commit_receipt.get("install_id") or "") != install_id
            or str(commit_receipt.get("pack_id") or "") != pack_id
            or str(commit_receipt.get("manifest_hash") or "") != manifest_hash
        ):
            error = "install_reconciliation_commit_receipt_mismatch"
            self.store.mark_projection(install_id, succeeded=False, error=error)
            return self._result(row, ok=False, error=error)

        install_receipt = dict(payload.get("install_commit_receipt") or {})
        filesystem_receipt = dict(install_receipt.get("filesystem") or {})
        try:
            self._verify_committed_target(
                pack_id=pack_id,
                manifest_hash=manifest_hash,
                filesystem_receipt=filesystem_receipt,
            )
        except Exception as exc:
            error = self._error(exc)
            self.store.mark_projection(install_id, succeeded=False, error=error)
            return self._result(row, ok=False, error=error)

        if row.get("projection_state") != "succeeded":
            try:
                manifest = dict(
                    (payload.get("pack_metadata") or {}).get(
                        "install_projection_manifest"
                    )
                    or {}
                )
                if not manifest:
                    raise RuntimeError("install_projection_manifest_missing")
                _sync_install_time_registries(
                    local_core_root=self.local_core_root,
                    capability_code=pack_id,
                    manifest=manifest,
                    result=_ProjectionResult(),
                )
                self.store.mark_projection(install_id, succeeded=True)
            except Exception as exc:
                error = self._error(exc)
                self.store.mark_projection(install_id, succeeded=False, error=error)
                return self._result(row, ok=False, error=error)

        if row.get("filesystem_cleanup_state") != "succeeded":
            try:
                finalize_committed_filesystem(
                    local_core_root=self.local_core_root,
                    install_id=install_id,
                    capability_code=pack_id,
                    manifest_hash=manifest_hash,
                    filesystem_receipt=filesystem_receipt,
                )
                self.store.mark_filesystem_cleanup(install_id, succeeded=True)
            except Exception as exc:
                error = self._error(exc)
                self.store.mark_filesystem_cleanup(
                    install_id,
                    succeeded=False,
                    error=error,
                )
                return self._result(row, ok=False, error=error)
        current = self.store.get(install_id) or row
        return self._result(current, ok=True, error=None)

    def _verify_committed_target(
        self,
        *,
        pack_id: str,
        manifest_hash: str,
        filesystem_receipt: dict[str, Any],
    ) -> None:
        expected_target = (
            self.local_core_root / "backend" / "app" / "capabilities" / pack_id
        ).resolve()
        target = Path(str(filesystem_receipt.get("target_cap_dir") or "")).resolve()
        if target != expected_target:
            raise RuntimeError("install_reconciliation_target_path_mismatch")
        manifest_path = target / "manifest.yaml"
        if not manifest_path.is_file():
            raise RuntimeError("install_reconciliation_target_manifest_missing")
        actual_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if actual_hash != manifest_hash:
            raise RuntimeError("install_reconciliation_target_manifest_hash_mismatch")

    @staticmethod
    def _error(exc: Exception) -> str:
        return f"{type(exc).__name__}:{str(exc)[:420]}"

    @staticmethod
    def _result(
        row: dict[str, Any],
        *,
        ok: bool,
        error: Optional[str],
    ) -> dict[str, Any]:
        return {
            "kind": "pack_install_reconciliation",
            "ok": ok,
            "install_id": str(row.get("install_id") or ""),
            "pack_id": str(row.get("pack_id") or ""),
            "projection_state": row.get("projection_state"),
            "filesystem_cleanup_state": row.get("filesystem_cleanup_state"),
            "error": error,
            "retry_after_seconds": 0 if ok else 30,
        }
