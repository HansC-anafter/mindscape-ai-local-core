"""Facade for persisting pack activation lifecycle state."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.services.install_result import InstallResult
from backend.app.services.pack_activation_helpers import PackActivationHelperMixin
from backend.app.services.pack_activation_types import PackActivationRecord, _utc_now
from backend.app.services.stores.pack_activation_state_store import PackActivationStateStore


class PackActivationService(PackActivationHelperMixin):
    """Derive and persist activation state from install/enable/disable events."""

    def __init__(self, store: Optional[PackActivationStateStore] = None):
        self.store = store or PackActivationStateStore()

    def get_state(self, pack_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_state(pack_id)

    def list_states_by_pack_id(self) -> Dict[str, Dict[str, Any]]:
        return self.store.list_states_by_pack_id()

    def record_install_outcome(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        install_result: InstallResult,
        enabled: bool,
        hot_reload_performed: bool,
        restart_required: bool,
        restart_decision: Optional[Dict[str, Any]] = None,
        manifest_path: Optional[Path] = None,
        activation_error: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self.build_install_record(
            pack_id=pack_id,
            manifest=manifest,
            install_result=install_result,
            enabled=enabled,
            hot_reload_performed=hot_reload_performed,
            restart_required=restart_required,
            restart_decision=restart_decision,
            manifest_path=manifest_path,
            activation_error=activation_error,
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_enabled(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        manifest_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        existing = self.store.get_state(pack_id)
        record = PackActivationRecord(
            pack_id=pack_id,
            pack_family=self._infer_pack_family(manifest),
            enabled=True,
            install_state=existing.get("install_state", "installed")
            if existing
            else "installed",
            migration_state=existing.get("migration_state", "unknown")
            if existing
            else "unknown",
            activation_state="pending_activation",
            activation_mode="manual_enable",
            embedding_state=self._derive_embedding_state(
                manifest=manifest,
                enabled=True,
                current_state=existing.get("embedding_state") if existing else None,
            ),
            embedding_error=None,
            embeddings_updated_at=self._coerce_dt(
                existing.get("embeddings_updated_at") if existing else None
            ),
            manifest_hash=self._compute_manifest_hash(manifest, manifest_path),
            registered_prefixes=self._extract_registered_prefixes(manifest, None),
            last_error=None,
            activated_at=None,
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_disabled(self, pack_id: str) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        record = PackActivationRecord(
            pack_id=pack_id,
            pack_family=existing["pack_family"],
            enabled=False,
            install_state=existing["install_state"],
            migration_state=existing["migration_state"],
            activation_state="disabled",
            activation_mode="manual_disable",
            embedding_state="disabled",
            embedding_error=None,
            embeddings_updated_at=self._coerce_dt(existing.get("embeddings_updated_at")),
            manifest_hash=existing.get("manifest_hash"),
            registered_prefixes=existing.get("registered_prefixes") or [],
            last_error=None,
            activated_at=None,
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_activation_pending(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        activation_mode: str,
        manifest_path: Optional[Path] = None,
        registered_prefixes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        existing = self.store.get_state(pack_id)
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state="pending_activation",
            activation_mode=activation_mode,
            manifest_path=manifest_path,
            registered_prefixes=registered_prefixes,
            last_error=None,
            activated_at=None,
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_activation_succeeded(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        activation_mode: str,
        manifest_path: Optional[Path] = None,
        registered_prefixes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        existing = self.store.get_state(pack_id)
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state="active",
            activation_mode=activation_mode,
            manifest_path=manifest_path,
            registered_prefixes=registered_prefixes,
            last_error=None,
            activated_at=_utc_now(),
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_activation_failed(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        activation_mode: str,
        error: str,
        manifest_path: Optional[Path] = None,
        registered_prefixes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        existing = self.store.get_state(pack_id)
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state="activation_failed",
            activation_mode=activation_mode,
            manifest_path=manifest_path,
            registered_prefixes=registered_prefixes,
            last_error=error,
            activated_at=None,
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_validation_pending(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        manifest_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state=existing.get("activation_state", "pending_activation"),
            activation_mode=existing.get("activation_mode", "unknown"),
            manifest_path=manifest_path,
            registered_prefixes=existing.get("registered_prefixes"),
            last_error=None,
            activated_at=self._coerce_dt(existing.get("activated_at")),
        )
        record.install_state = "validation_pending"
        return self.store.upsert_state(**record.to_store_payload())

    def record_validation_succeeded(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        manifest_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state=existing.get("activation_state", "pending_activation"),
            activation_mode=existing.get("activation_mode", "unknown"),
            manifest_path=manifest_path,
            registered_prefixes=existing.get("registered_prefixes"),
            last_error=None,
            activated_at=self._coerce_dt(existing.get("activated_at")),
        )
        record.install_state = "installed"
        return self.store.upsert_state(**record.to_store_payload())

    def record_validation_failed(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        error: str,
        manifest_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state=existing.get("activation_state", "pending_activation"),
            activation_mode=existing.get("activation_mode", "unknown"),
            manifest_path=manifest_path,
            registered_prefixes=existing.get("registered_prefixes"),
            last_error=error,
            activated_at=self._coerce_dt(existing.get("activated_at")),
        )
        record.install_state = "validation_failed"
        return self.store.upsert_state(**record.to_store_payload())

    def record_embedding_succeeded(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        manifest_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state=existing.get("activation_state", "active"),
            activation_mode=existing.get("activation_mode", "unknown"),
            manifest_path=manifest_path,
            registered_prefixes=existing.get("registered_prefixes"),
            last_error=existing.get("last_error"),
            activated_at=self._coerce_dt(existing.get("activated_at")),
            embedding_state=self._derive_embedding_state(
                manifest=manifest,
                enabled=bool(existing.get("enabled", True)),
                current_state=existing.get("embedding_state"),
                indexed=True,
            ),
            embedding_error=None,
            embeddings_updated_at=_utc_now(),
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_embedding_failed(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        error: str,
        manifest_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state=existing.get("activation_state", "active"),
            activation_mode=existing.get("activation_mode", "unknown"),
            manifest_path=manifest_path,
            registered_prefixes=existing.get("registered_prefixes"),
            last_error=existing.get("last_error"),
            activated_at=self._coerce_dt(existing.get("activated_at")),
            embedding_state=self._derive_embedding_state(
                manifest=manifest,
                enabled=bool(existing.get("enabled", True)),
                current_state=existing.get("embedding_state"),
                failed=True,
            ),
            embedding_error=error,
            embeddings_updated_at=self._coerce_dt(existing.get("embeddings_updated_at")),
        )
        return self.store.upsert_state(**record.to_store_payload())

    def record_embedding_observed(
        self,
        *,
        pack_id: str,
        row_count: int,
        latest_updated_at: Optional[datetime],
        manifest: Optional[Dict[str, Any]] = None,
        manifest_path: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        existing = self.store.get_state(pack_id)
        if existing is None:
            return None
        if manifest is None and manifest_path is None:
            manifest, manifest_path = self._load_runtime_manifest(pack_id)
        observed_state = self._derive_observed_embedding_state(
            manifest=manifest,
            enabled=bool(existing.get("enabled", True)),
            current_state=existing.get("embedding_state"),
            row_count=row_count,
        )
        record = self._build_runtime_record(
            pack_id=pack_id,
            manifest=manifest,
            existing=existing,
            activation_state=existing.get("activation_state", "active"),
            activation_mode=existing.get("activation_mode", "unknown"),
            manifest_path=manifest_path,
            registered_prefixes=existing.get("registered_prefixes"),
            last_error=existing.get("last_error"),
            activated_at=self._coerce_dt(existing.get("activated_at")),
            embedding_state=observed_state,
            embedding_error=existing.get("embedding_error")
            if observed_state == "failed"
            else None,
            embeddings_updated_at=latest_updated_at
            if observed_state == "indexed"
            else self._coerce_dt(existing.get("embeddings_updated_at")),
        )
        return self.store.upsert_state(**record.to_store_payload())

    def build_install_record(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        install_result: InstallResult,
        enabled: bool,
        hot_reload_performed: bool,
        restart_required: bool,
        restart_decision: Optional[Dict[str, Any]] = None,
        manifest_path: Optional[Path] = None,
        activation_error: Optional[str] = None,
    ) -> PackActivationRecord:
        backend_process_restart_required = bool(
            (restart_decision or {}).get(
                "backend_process_restart_required",
                restart_required,
            )
        )
        migration_state = self._derive_migration_state(pack_id, install_result)
        if not enabled:
            activation_state = "disabled"
            activation_mode = "install_disabled"
            activated_at = None
        elif hot_reload_performed:
            activation_state = "active"
            activation_mode = "install_hot_reload"
            activated_at = _utc_now()
        elif backend_process_restart_required:
            activation_state = "pending_restart"
            activation_mode = "pending_restart"
            activated_at = None
        else:
            activation_state = "pending_activation"
            activation_mode = "install_registered"
            activated_at = None

        last_error = activation_error or (install_result.errors[0] if install_result.errors else None)
        return PackActivationRecord(
            pack_id=pack_id,
            pack_family=self._infer_pack_family(manifest),
            enabled=enabled,
            install_state="installed",
            migration_state=migration_state,
            activation_state=activation_state,
            activation_mode=activation_mode,
            embedding_state=self._derive_embedding_state(
                manifest=manifest,
                enabled=enabled,
                current_state=None,
            ),
            embedding_error=None,
            embeddings_updated_at=None,
            manifest_hash=self._compute_manifest_hash(manifest, manifest_path),
            registered_prefixes=self._extract_registered_prefixes(
                manifest, install_result
            ),
            last_error=last_error,
            activated_at=activated_at,
        )
