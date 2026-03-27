"""Helpers for persisting pack activation lifecycle state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import yaml

from app.services.install_result import InstallResult
from app.services.stores.pack_activation_state_store import PackActivationStateStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PackActivationRecord:
    pack_id: str
    pack_family: str
    enabled: bool
    install_state: str
    migration_state: str
    activation_state: str
    activation_mode: str
    embedding_state: str
    embedding_error: Optional[str]
    embeddings_updated_at: Optional[datetime]
    manifest_hash: Optional[str]
    registered_prefixes: List[str]
    last_error: Optional[str]
    activated_at: Optional[datetime]

    def to_store_payload(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_family": self.pack_family,
            "enabled": self.enabled,
            "install_state": self.install_state,
            "migration_state": self.migration_state,
            "activation_state": self.activation_state,
            "activation_mode": self.activation_mode,
            "embedding_state": self.embedding_state,
            "embedding_error": self.embedding_error,
            "embeddings_updated_at": self.embeddings_updated_at,
            "manifest_hash": self.manifest_hash,
            "registered_prefixes": self.registered_prefixes,
            "last_error": self.last_error,
            "activated_at": self.activated_at,
        }


class PackActivationService:
    """Derive and persist activation state from install/enable/disable events."""

    def __init__(self, store: Optional[PackActivationStateStore] = None):
        self.store = store or PackActivationStateStore()

    def get_state(self, pack_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_state(pack_id)

    def record_install_outcome(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        install_result: InstallResult,
        enabled: bool,
        hot_reload_performed: bool,
        restart_required: bool,
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
        manifest_path: Optional[Path] = None,
        activation_error: Optional[str] = None,
    ) -> PackActivationRecord:
        migration_state = self._derive_migration_state(pack_id, install_result)
        if not enabled:
            activation_state = "disabled"
            activation_mode = "install_disabled"
            activated_at = None
        elif hot_reload_performed:
            activation_state = "active"
            activation_mode = "install_hot_reload"
            activated_at = _utc_now()
        elif restart_required:
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

    def _derive_migration_state(
        self, pack_id: str, install_result: Optional[InstallResult]
    ) -> str:
        if install_result and install_result.migration_status:
            state = install_result.migration_status.get(pack_id)
            if state:
                return state
        if install_result and install_result.installed.get("migrations"):
            return "unknown"
        return "not_applicable"

    def _infer_pack_family(self, manifest: Optional[Dict[str, Any]]) -> str:
        manifest = manifest or {}
        has_routes = bool(manifest.get("routes"))
        has_capability_surface = any(
            manifest.get(key)
            for key in ("playbooks", "tools", "ui_components", "api_endpoints")
        ) or bool(manifest.get("code"))
        if has_routes and has_capability_surface:
            return "hybrid"
        if has_routes:
            return "feature_pack"
        return "capability_api"

    def _compute_manifest_hash(
        self, manifest: Optional[Dict[str, Any]], manifest_path: Optional[Path]
    ) -> Optional[str]:
        try:
            if manifest_path and Path(manifest_path).exists():
                return hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()
            if manifest:
                payload = json.dumps(
                    manifest, sort_keys=True, ensure_ascii=False, default=str
                ).encode("utf-8")
                return hashlib.sha256(payload).hexdigest()
        except Exception:
            return None
        return None

    def _extract_registered_prefixes(
        self,
        manifest: Optional[Dict[str, Any]],
        install_result: Optional[InstallResult],
    ) -> List[str]:
        prefixes: List[str] = []
        manifest = manifest or {}
        prefixes.extend(self._normalize_values(manifest.get("routes")))
        apis = manifest.get("apis")
        if isinstance(apis, list):
            for api_def in apis:
                if isinstance(api_def, dict):
                    prefixes.extend(self._normalize_values(api_def.get("prefix")))
        if install_result:
            prefixes.extend(
                self._normalize_values(install_result.installed.get("api_endpoints"))
            )
        deduped: List[str] = []
        seen = set()
        for item in prefixes:
            if item and item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _normalize_values(self, values: Any) -> List[str]:
        if not values:
            return []
        if isinstance(values, str):
            return [values]
        if isinstance(values, Iterable):
            normalized: List[str] = []
            for item in values:
                if isinstance(item, str):
                    normalized.append(item)
            return normalized
        return []

    def _build_runtime_record(
        self,
        *,
        pack_id: str,
        manifest: Optional[Dict[str, Any]],
        existing: Optional[Dict[str, Any]],
        activation_state: str,
        activation_mode: str,
        manifest_path: Optional[Path],
        registered_prefixes: Optional[List[str]],
        last_error: Optional[str],
        activated_at: Optional[datetime],
        embedding_state: Optional[str] = None,
        embedding_error: Optional[str] = None,
        embeddings_updated_at: Optional[datetime] = None,
    ) -> PackActivationRecord:
        existing = existing or {}
        merged_prefixes = self._merge_registered_prefixes(
            existing.get("registered_prefixes"), registered_prefixes
        )
        return PackActivationRecord(
            pack_id=pack_id,
            pack_family=existing.get("pack_family") or self._infer_pack_family(manifest),
            enabled=bool(existing.get("enabled", True)),
            install_state=existing.get("install_state", "installed"),
            migration_state=existing.get("migration_state", "unknown"),
            activation_state=activation_state,
            activation_mode=activation_mode,
            embedding_state=embedding_state
            or self._derive_embedding_state(
                manifest=manifest,
                enabled=bool(existing.get("enabled", True)),
                current_state=existing.get("embedding_state"),
            ),
            embedding_error=embedding_error
            if embedding_error is not None
            else existing.get("embedding_error"),
            embeddings_updated_at=embeddings_updated_at
            or self._coerce_dt(existing.get("embeddings_updated_at")),
            manifest_hash=self._compute_manifest_hash(manifest, manifest_path)
            or existing.get("manifest_hash"),
            registered_prefixes=merged_prefixes,
            last_error=last_error,
            activated_at=activated_at,
        )

    def _merge_registered_prefixes(self, *groups: Any) -> List[str]:
        merged: List[str] = []
        seen = set()
        for group in groups:
            for item in self._normalize_values(group):
                if item and item not in seen:
                    seen.add(item)
                    merged.append(item)
        return merged

    def _derive_embedding_state(
        self,
        *,
        manifest: Optional[Dict[str, Any]],
        enabled: bool,
        current_state: Optional[str],
        indexed: bool = False,
        failed: bool = False,
    ) -> str:
        if not enabled:
            return "disabled"
        if not self._embedding_applicable(manifest):
            return "not_applicable"
        if indexed:
            return "indexed"
        if failed:
            return "failed"
        if current_state in {"indexed", "failed", "pending"}:
            return current_state
        return "pending"

    def _derive_observed_embedding_state(
        self,
        *,
        manifest: Optional[Dict[str, Any]],
        enabled: bool,
        current_state: Optional[str],
        row_count: int,
    ) -> str:
        if not enabled:
            return "disabled"
        if not self._embedding_applicable(manifest):
            return "not_applicable"
        if row_count > 0:
            return "indexed"
        if current_state == "failed":
            return "failed"
        return "pending"

    def _embedding_applicable(self, manifest: Optional[Dict[str, Any]]) -> bool:
        manifest = manifest or {}
        return bool(manifest.get("tools")) or bool(manifest.get("playbooks"))

    def _load_runtime_manifest(
        self, pack_id: str
    ) -> tuple[Optional[Dict[str, Any]], Optional[Path]]:
        manifest_path = (
            Path(__file__).resolve().parents[1]
            / "capabilities"
            / pack_id
            / "manifest.yaml"
        )
        if not manifest_path.exists():
            return None, None
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                return yaml.safe_load(handle) or {}, manifest_path
        except Exception:
            return None, manifest_path

    def _coerce_dt(self, value: Any) -> Optional[datetime]:
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None
