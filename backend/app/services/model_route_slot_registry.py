"""
Model route slot registry.

Builds one canonical inventory for all model-routing-related surfaces:
- local-core system settings
- installed/available capability pack manifests
- registered runtime environments

The registry is intentionally conservative: it supports an explicit manifest
contract (`model_routing.slots`) and also infers slots from today's manifest
shapes so existing packs are not invisible while they migrate.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.stores.installed_packs_store import InstalledPacksStore
from backend.app.models.runtime_environment import RuntimeEnvironment
from backend.app.services.model_route_slot_local_core import (
    collect_local_core_model_route_slots,
)
from backend.app.services.model_route_slot_manifest import (
    collect_playbook_route_summary,
    collect_route_dependency_codes,
    collect_tool_route_summary,
    extract_pack_slots_from_manifest_data,
)
from backend.app.services.model_route_slot_schema import (
    ModelRouteSlot,
    build_model_route_slot,
    slug_model_route_value,
    summarize_model_route_mapping,
    summarize_model_route_value,
)
from backend.app.services.model_route_slot_storage import (
    canonicalize_slots,
    coerce_slot_count,
    normalize_stored_slots,
    pack_slot_registration_changed,
)
from backend.app.services.runtime_route_registration import (
    build_runtime_registration_group,
    list_built_in_runtime_environments,
    sync_runtime_registration_metadata,
)
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


class ModelRouteSlotRegistry:
    def __init__(
        self,
        *,
        installed_packs_store: Optional[InstalledPacksStore] = None,
        system_settings_store: Optional[SystemSettingsStore] = None,
    ) -> None:
        self._installed_packs_store = installed_packs_store or InstalledPacksStore()
        self._system_settings_store = system_settings_store or SystemSettingsStore()

    def collect_inventory(
        self,
        *,
        db: Optional[Session] = None,
        installed_only: bool = True,
    ) -> Dict[str, Any]:
        pack_metas = self._load_pack_metas()
        installed_rows = {
            row["pack_id"]: row
            for row in self._installed_packs_store.list_installed_metadata()
        }
        enabled_ids = set(self._installed_packs_store.list_enabled_pack_ids())

        pack_groups: List[Dict[str, Any]] = []
        pack_coverage: List[Dict[str, Any]] = []

        pack_ids = set(pack_metas.keys()) | set(installed_rows.keys())
        for pack_id in sorted(pack_ids):
            installed_row = installed_rows.get(pack_id)
            installed = installed_row is not None
            if installed_only and not installed:
                continue

            pack_meta = pack_metas.get(pack_id)
            stored_metadata = (installed_row or {}).get("metadata") or {}
            stored_slots = self._normalize_stored_slots(
                stored_metadata.get("model_route_slots") or [],
                pack_id=pack_id,
                owner_name=(
                    (pack_meta or {}).get("display_name")
                    or (pack_meta or {}).get("name")
                    or pack_id
                ),
                installed=installed,
                enabled=pack_id in enabled_ids,
            )

            live_slots = (
                self.extract_pack_slots_from_manifest(
                    pack_id=pack_id,
                    pack_meta=pack_meta,
                    manifest_path=(pack_meta or {}).get("_file_path"),
                    installed=installed,
                    enabled=pack_id in enabled_ids,
                )
                if pack_meta
                else []
            )
            display_slots = live_slots or stored_slots
            stored_slot_count = self._coerce_slot_count(
                stored_metadata.get("model_route_slot_count"),
                fallback=len(stored_slots),
            )
            live_slot_count = len(live_slots)
            display_slot_count = len(display_slots)
            drift = installed and stored_slot_count != live_slot_count
            owner_name = (
                (pack_meta or {}).get("display_name")
                or (pack_meta or {}).get("name")
                or pack_id
            )

            coverage_entry = {
                "pack_id": pack_id,
                "name": owner_name,
                "installed": installed,
                "enabled": pack_id in enabled_ids,
                "manifest_path": (pack_meta or {}).get("_file_path"),
                "slot_count": display_slot_count,
                "live_slot_count": live_slot_count,
                "stored_slot_count": stored_slot_count,
                "registration_drift": drift,
                "slot_kinds": sorted(
                    {
                        str(slot.get("slot_kind") or "")
                        for slot in display_slots
                        if slot.get("slot_kind")
                    }
                ),
            }
            pack_coverage.append(coverage_entry)

            if display_slots:
                pack_groups.append(
                    {
                        "pack_id": pack_id,
                        "name": owner_name,
                        "installed": installed,
                        "enabled": pack_id in enabled_ids,
                        "manifest_path": (pack_meta or {}).get("_file_path"),
                        "slot_count": display_slot_count,
                        "slot_kinds": coverage_entry["slot_kinds"],
                        "registration_drift": drift,
                        "slots": display_slots,
                    }
                )

        local_core_slots = self._collect_local_core_slots()
        registered_runtimes = self._collect_runtime_groups(db)

        summary = {
            "total_slot_count": len(local_core_slots)
            + sum(group["slot_count"] for group in pack_groups)
            + sum(group["slot_count"] for group in registered_runtimes),
            "local_core_slot_count": len(local_core_slots),
            "installed_pack_count_scanned": sum(
                1 for item in pack_coverage if item["installed"]
            ),
            "installed_pack_count_with_slots": sum(
                1
                for item in pack_coverage
                if item["installed"] and item["slot_count"] > 0
            ),
            "installed_pack_slot_count": sum(
                group["slot_count"] for group in pack_groups if group["installed"]
            ),
            "registered_runtime_count": len(registered_runtimes),
            "registered_runtime_slot_count": sum(
                group["slot_count"] for group in registered_runtimes
            ),
            "packs_with_registration_drift": [
                item["pack_id"] for item in pack_coverage if item["registration_drift"]
            ],
        }

        return {
            "summary": summary,
            "local_core_slots": local_core_slots,
            "pack_groups": pack_groups,
            "pack_coverage": pack_coverage,
            "registered_runtimes": registered_runtimes,
        }

    def reconcile_installed_pack_registrations(
        self,
        *,
        installed_only: bool = True,
    ) -> Dict[str, Any]:
        pack_metas = self._load_pack_metas()
        installed_rows = {
            row["pack_id"]: row
            for row in self._installed_packs_store.list_installed_metadata()
        }
        enabled_ids = set(self._installed_packs_store.list_enabled_pack_ids())

        updated: List[str] = []
        unchanged: List[str] = []
        missing_manifest: List[str] = []

        pack_ids = sorted(
            installed_rows.keys()
            if installed_only
            else set(pack_metas.keys()) | set(installed_rows.keys())
        )
        for pack_id in pack_ids:
            installed_row = installed_rows.get(pack_id)
            if installed_only and installed_row is None:
                continue
            if installed_row is None:
                continue

            pack_meta = pack_metas.get(pack_id)
            if not pack_meta:
                missing_manifest.append(pack_id)
                continue

            stored_metadata = (installed_row or {}).get("metadata") or {}
            stored_slots = self._normalize_stored_slots(
                stored_metadata.get("model_route_slots") or [],
                pack_id=pack_id,
                owner_name=(
                    str(
                        pack_meta.get("display_name")
                        or pack_meta.get("name")
                        or pack_id
                    ).strip()
                    or pack_id
                ),
                installed=installed_row is not None,
                enabled=pack_id in enabled_ids,
            )
            live_slots = self.extract_pack_slots_from_manifest(
                pack_id=pack_id,
                pack_meta=pack_meta,
                manifest_path=pack_meta.get("_file_path"),
                installed=installed_row is not None,
                enabled=pack_id in enabled_ids,
            )

            if not self._pack_slot_registration_changed(
                stored_slots=stored_slots,
                stored_slot_count=stored_metadata.get("model_route_slot_count"),
                live_slots=live_slots,
            ):
                unchanged.append(pack_id)
                continue

            self._installed_packs_store.update_metadata(
                pack_id,
                {
                    "model_route_slots": live_slots,
                    "model_route_slot_count": len(live_slots),
                    "model_route_slot_reconciled_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                },
            )
            updated.append(pack_id)

        return {
            "scanned_pack_count": len(pack_ids),
            "updated_pack_count": len(updated),
            "unchanged_pack_count": len(unchanged),
            "missing_manifest_count": len(missing_manifest),
            "updated_pack_ids": updated,
            "unchanged_pack_ids": unchanged,
            "missing_manifest_pack_ids": missing_manifest,
        }

    def reconcile_runtime_registrations(
        self,
        *,
        db: Optional[Session],
    ) -> Dict[str, Any]:
        if db is None:
            return {
                "scanned_runtime_count": 0,
                "updated_runtime_count": 0,
                "unchanged_runtime_count": 0,
                "updated_runtime_ids": [],
                "unchanged_runtime_ids": [],
            }

        updated: List[str] = []
        unchanged: List[str] = []
        for runtime in db.query(RuntimeEnvironment).all():
            group = build_runtime_registration_group(runtime)
            if not group["registration_drift"]:
                unchanged.append(runtime.id)
                continue
            sync_runtime_registration_metadata(runtime)
            updated.append(runtime.id)

        if updated:
            db.commit()

        return {
            "scanned_runtime_count": len(updated) + len(unchanged),
            "updated_runtime_count": len(updated),
            "unchanged_runtime_count": len(unchanged),
            "updated_runtime_ids": updated,
            "unchanged_runtime_ids": unchanged,
        }

    def extract_pack_slots_from_manifest(
        self,
        *,
        pack_id: str,
        pack_meta: Optional[Dict[str, Any]],
        manifest_path: Optional[str] = None,
        installed: bool = False,
        enabled: bool = False,
    ) -> List[Dict[str, Any]]:
        return extract_pack_slots_from_manifest_data(
            pack_id=pack_id,
            pack_meta=pack_meta,
            manifest_path=manifest_path,
            installed=installed,
            enabled=enabled,
        )

    def _load_pack_metas(self) -> Dict[str, Dict[str, Any]]:
        from backend.app.routes.core.capability_packs import _scan_pack_yaml_files

        metas: Dict[str, Dict[str, Any]] = {}
        for pack_meta in _scan_pack_yaml_files():
            if not isinstance(pack_meta, dict):
                continue
            pack_id = str(pack_meta.get("id") or pack_meta.get("code") or "").strip()
            if not pack_id:
                continue
            metas[pack_id] = pack_meta
        return metas

    def _collect_local_core_slots(self) -> List[Dict[str, Any]]:
        return collect_local_core_model_route_slots(self._system_settings_store)

    def _collect_runtime_groups(self, db: Optional[Session]) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = list_built_in_runtime_environments()
        groups = [build_runtime_registration_group(runtime) for runtime in groups]

        if db is None:
            return groups

        for runtime in db.query(RuntimeEnvironment).all():
            groups.append(build_runtime_registration_group(runtime))
        return groups

    @staticmethod
    def _collect_route_dependency_codes(dependencies: Any) -> List[str]:
        return collect_route_dependency_codes(dependencies)

    @staticmethod
    def _collect_tool_route_summary(tools: Any) -> Dict[str, List[Any]]:
        return collect_tool_route_summary(tools)

    @staticmethod
    def _collect_playbook_route_summary(playbooks: Any) -> List[str]:
        return collect_playbook_route_summary(playbooks)

    @staticmethod
    def _normalize_stored_slots(
        stored_slots: Sequence[Any],
        *,
        pack_id: str,
        owner_name: str,
        installed: bool,
        enabled: bool,
    ) -> List[Dict[str, Any]]:
        return normalize_stored_slots(
            stored_slots,
            pack_id=pack_id,
            owner_name=owner_name,
            installed=installed,
            enabled=enabled,
        )

    @staticmethod
    def _coerce_slot_count(value: Any, *, fallback: int) -> int:
        return coerce_slot_count(value, fallback=fallback)

    @staticmethod
    def _pack_slot_registration_changed(
        *,
        stored_slots: Sequence[Dict[str, Any]],
        stored_slot_count: Any,
        live_slots: Sequence[Dict[str, Any]],
    ) -> bool:
        return pack_slot_registration_changed(
            stored_slots=stored_slots,
            stored_slot_count=stored_slot_count,
            live_slots=live_slots,
        )

    @staticmethod
    def _canonicalize_slots(slots: Sequence[Dict[str, Any]]) -> List[str]:
        return canonicalize_slots(slots)

    @staticmethod
    def _summarize_mapping(value: Any) -> str:
        return summarize_model_route_mapping(value)

    @staticmethod
    def _summarize_value(value: Any) -> str:
        return summarize_model_route_value(value)

    @staticmethod
    def _slug(value: Any) -> str:
        return slug_model_route_value(value)

    def _build_slot(
        self,
        *,
        pack_id: str,
        owner_name: str,
        slot_kind: str,
        title: str,
        summary: str,
        route_family: str,
        source: str,
        evidence_path: Optional[str],
        installed: Optional[bool],
        enabled: Optional[bool],
        raw: Optional[Dict[str, Any]] = None,
        owner_kind: str = "pack",
        settings_anchor: str = "basic:model-routing-registry",
    ) -> ModelRouteSlot:
        return build_model_route_slot(
            pack_id=pack_id,
            owner_name=owner_name,
            slot_kind=slot_kind,
            title=title,
            summary=summary,
            route_family=route_family,
            source=source,
            evidence_path=evidence_path,
            installed=installed,
            enabled=enabled,
            raw=raw,
            owner_kind=owner_kind,
            settings_anchor=settings_anchor,
        )
