"""Pure helper seams for pack activation state derivation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from backend.app.services.install_result import InstallResult
from backend.app.services.pack_activation_types import PackActivationRecord


class PackActivationHelperMixin:
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
