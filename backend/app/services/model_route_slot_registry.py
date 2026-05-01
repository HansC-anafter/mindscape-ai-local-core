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

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.services.stores.installed_packs_store import InstalledPacksStore
from backend.app.models.runtime_environment import RuntimeEnvironment
from backend.app.services.runtime_route_registration import (
    build_runtime_registration_group,
    list_built_in_runtime_environments,
    sync_runtime_registration_metadata,
)
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)

_ROUTE_DEPENDENCY_CODES = frozenset({"core_llm", "shared_llm"})
_ROUTE_SETTINGS_PANEL_SECTIONS = frozenset(
    {"model-routing", "runtime-environments", "workflow-engines"}
)
_SYSTEM_SETTING_SLOTS = (
    (
        "default_llm_provider",
        "Default LLM Provider",
        "llm_provider_default",
        "basic:models-and-quota",
    ),
    (
        "enable_capability_profile",
        "Governed Capability Profiles",
        "stage_profile_gate",
        "basic:models-and-quota",
    ),
    ("chat_model", "Legacy Chat Model", "chat_model_default", "basic:llm-chat"),
    (
        "embedding_model",
        "Embedding Model",
        "embedding_model_default",
        "basic:embedding",
    ),
    (
        "gemini_cli_auth_mode",
        "Gemini CLI Auth Mode",
        "runtime_auth_mode",
        "tab:runtime",
    ),
    (
        "agent_cli_model",
        "Gemini CLI Agent Model",
        "runtime_agent_model",
        "tab:runtime",
    ),
)


@dataclass
class ModelRouteSlot:
    slot_id: str
    owner_kind: str
    owner_id: str
    owner_name: str
    slot_kind: str
    title: str
    summary: str
    route_family: str
    source: str
    settings_anchor: str = "basic:model-routing-registry"
    installed: Optional[bool] = None
    enabled: Optional[bool] = None
    evidence_path: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["raw"] = dict(self.raw or {})
        return payload


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
            row["pack_id"]: row for row in self._installed_packs_store.list_installed_metadata()
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
                    {str(slot.get("slot_kind") or "") for slot in display_slots if slot.get("slot_kind")}
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
                1 for item in pack_coverage if item["installed"] and item["slot_count"] > 0
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
            row["pack_id"]: row for row in self._installed_packs_store.list_installed_metadata()
        }
        enabled_ids = set(self._installed_packs_store.list_enabled_pack_ids())

        updated: List[str] = []
        unchanged: List[str] = []
        missing_manifest: List[str] = []

        pack_ids = sorted(installed_rows.keys() if installed_only else set(pack_metas.keys()) | set(installed_rows.keys()))
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
                    str(pack_meta.get("display_name") or pack_meta.get("name") or pack_id).strip()
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
                    "model_route_slot_reconciled_at": datetime.now(timezone.utc).isoformat(),
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
        if not isinstance(pack_meta, dict):
            return []

        owner_name = (
            str(pack_meta.get("display_name") or pack_meta.get("name") or pack_id).strip()
            or pack_id
        )
        evidence_path = manifest_path or pack_meta.get("_file_path")

        slots: List[ModelRouteSlot] = []
        slots.extend(
            self._extract_explicit_manifest_slots(
                pack_id=pack_id,
                pack_meta=pack_meta,
                owner_name=owner_name,
                evidence_path=evidence_path,
                installed=installed,
                enabled=enabled,
            )
        )

        runtime_affinity = str(pack_meta.get("runtime_affinity") or "").strip()
        if runtime_affinity:
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="runtime_affinity",
                    title="Runtime Affinity",
                    summary=runtime_affinity,
                    route_family="runtime_lane",
                    source="manifest.runtime_affinity",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"runtime_affinity": runtime_affinity},
                )
            )

        runtime_provider = pack_meta.get("runtime_provider")
        if runtime_provider:
            provider_summary = self._summarize_mapping(runtime_provider)
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="runtime_provider",
                    title="Runtime Provider",
                    summary=provider_summary,
                    route_family="runtime_provider",
                    source="manifest.runtime_provider",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"runtime_provider": runtime_provider},
                )
            )

        models = pack_meta.get("models")
        if isinstance(models, list) and models:
            providers = sorted(
                {
                    str(model.get("provider") or "").strip()
                    for model in models
                    if isinstance(model, dict) and str(model.get("provider") or "").strip()
                }
            )
            roles = sorted(
                {
                    str(model.get("role") or "").strip()
                    for model in models
                    if isinstance(model, dict) and str(model.get("role") or "").strip()
                }
            )
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="model_catalog",
                    title="Model Catalog",
                    summary=(
                        f"{len(models)} model definitions"
                        + (f"; providers={', '.join(providers)}" if providers else "")
                        + (f"; roles={', '.join(roles[:4])}" if roles else "")
                    ),
                    route_family="model_catalog",
                    source="manifest.models",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={
                        "model_count": len(models),
                        "providers": providers,
                        "roles": roles,
                    },
                )
            )

        dependency_codes = self._collect_route_dependency_codes(pack_meta.get("dependencies"))
        if dependency_codes:
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="llm_dependency",
                    title="Shared LLM Dependency",
                    summary=", ".join(sorted(dependency_codes)),
                    route_family="shared_llm_dependency",
                    source="manifest.dependencies",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"dependencies": sorted(dependency_codes)},
                )
            )

        tool_route_summary = self._collect_tool_route_summary(pack_meta.get("tools"))
        if tool_route_summary:
            slots.extend(
                self._build_tool_summary_slots(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    tool_route_summary=tool_route_summary,
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                )
            )

        playbook_summary = self._collect_playbook_route_summary(pack_meta.get("playbooks"))
        if playbook_summary:
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="playbook_route_dependency",
                    title="Playbook Route Dependencies",
                    summary=(
                        f"{len(playbook_summary)} playbooks reference routed LLM tools; "
                        f"examples={', '.join(playbook_summary[:4])}"
                    ),
                    route_family="playbook_dependency",
                    source="manifest.playbooks",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"playbooks": playbook_summary},
                )
            )

        slots.extend(
            self._extract_settings_panel_slots(
                pack_id=pack_id,
                pack_meta=pack_meta,
                owner_name=owner_name,
                evidence_path=evidence_path,
                installed=installed,
                enabled=enabled,
            )
        )

        return [slot.to_dict() for slot in slots]

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
        slots: List[Dict[str, Any]] = []
        for key, title, slot_kind, settings_anchor in _SYSTEM_SETTING_SLOTS:
            setting = self._system_settings_store.get_setting(key)
            if setting is None:
                continue
            if setting.value in (None, "", {}, []):
                continue
            slots.append(
                self._build_slot(
                    pack_id="local-core",
                    owner_name="Local-Core",
                    slot_kind=slot_kind,
                    title=title,
                    summary=self._summarize_value(setting.value),
                    route_family="local_core_setting",
                    source=f"system_settings.{key}",
                    evidence_path=None,
                    installed=True,
                    enabled=True,
                    owner_kind="local_core",
                    settings_anchor=settings_anchor,
                    raw={
                        "key": key,
                        "value": setting.value,
                        "category": setting.category,
                        "description": setting.description,
                    },
                ).to_dict()
            )

        capability_profile_mapping = (
            self._system_settings_store.get_capability_profile_mapping()
        )
        if capability_profile_mapping:
            slots.append(
                self._build_slot(
                    pack_id="local-core",
                    owner_name="Local-Core",
                    slot_kind="capability_profile_mapping",
                    title="Stage to Capability Profile Mapping",
                    summary=self._summarize_value(capability_profile_mapping),
                    route_family="stage_mapping",
                    source="system_settings.capability_profile_mapping",
                    evidence_path=None,
                    installed=True,
                    enabled=True,
                    owner_kind="local_core",
                    settings_anchor="basic:models-and-quota",
                    raw={"mapping": capability_profile_mapping},
                ).to_dict()
            )

        from backend.app.services.model_routing_policy_service import (
            ModelRoutingPolicyService,
        )
        from backend.app.services.executor_routing_policy_service import (
            ExecutorRoutingPolicyService,
        )

        local_profile_bindings = ModelRoutingPolicyService(
            settings_store=self._system_settings_store
        ).get_profile_bindings_for_scope("local")
        if local_profile_bindings:
            slots.append(
                self._build_slot(
                    pack_id="local-core",
                    owner_name="Local-Core",
                    slot_kind="profile_model_bindings_local",
                    title="Local Scoped Profile Bindings",
                    summary=self._summarize_value(local_profile_bindings),
                    route_family="profile_model_binding",
                    source="system_settings.profile_model_bindings.local",
                    evidence_path=None,
                    installed=True,
                    enabled=True,
                    owner_kind="local_core",
                    settings_anchor="basic:models-and-quota",
                    raw={"bindings": local_profile_bindings},
                ).to_dict()
            )

        profile_model_bindings = self._system_settings_store.get_profile_model_bindings()
        if profile_model_bindings:
            slots.append(
                self._build_slot(
                    pack_id="local-core",
                    owner_name="Local-Core",
                    slot_kind="profile_model_bindings",
                    title="Scoped Profile Model Bindings",
                    summary=self._summarize_value(profile_model_bindings),
                    route_family="profile_model_binding",
                    source="system_settings.profile_model_bindings",
                    evidence_path=None,
                    installed=True,
                    enabled=True,
                    owner_kind="local_core",
                    settings_anchor="basic:models-and-quota",
                    raw={"bindings": profile_model_bindings},
                ).to_dict()
            )

        executor_policy = ExecutorRoutingPolicyService.build_registry_summary()
        slots.append(
            self._build_slot(
                pack_id="local-core",
                owner_name="Local-Core",
                slot_kind="executor_route_policy",
                title="Workspace Executor Runtime Policy",
                summary="authority=model-routing-registry; surfaces=codex_cli, gemini_cli",
                route_family="executor_runtime_policy",
                source="model_routing_registry.executor_route_policy",
                evidence_path=None,
                installed=True,
                enabled=True,
                owner_kind="local_core",
                settings_anchor="basic:model-routing-registry",
                raw=executor_policy,
            ).to_dict()
        )
        slots.append(
            self._build_slot(
                pack_id="local-core",
                owner_name="Local-Core",
                slot_kind="runtime_substitution_policy",
                title="Runtime Substitution Policy",
                summary=self._summarize_value(
                    executor_policy.get("fallback_policy", {})
                ),
                route_family="executor_runtime_policy",
                source="model_routing_registry.executor_route_policy.fallback_policy",
                evidence_path=None,
                installed=True,
                enabled=True,
                owner_kind="local_core",
                settings_anchor="basic:model-routing-registry",
                raw=executor_policy.get("fallback_policy", {}),
            ).to_dict()
        )

        return slots

    def _collect_runtime_groups(self, db: Optional[Session]) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = list_built_in_runtime_environments()
        groups = [build_runtime_registration_group(runtime) for runtime in groups]

        if db is None:
            return groups

        for runtime in db.query(RuntimeEnvironment).all():
            groups.append(build_runtime_registration_group(runtime))
        return groups

    def _extract_explicit_manifest_slots(
        self,
        *,
        pack_id: str,
        pack_meta: Dict[str, Any],
        owner_name: str,
        evidence_path: Optional[str],
        installed: bool,
        enabled: bool,
    ) -> List[ModelRouteSlot]:
        model_routing = pack_meta.get("model_routing")
        if not isinstance(model_routing, dict):
            return []

        slots: List[ModelRouteSlot] = []
        for index, slot in enumerate(model_routing.get("slots") or []):
            if not isinstance(slot, dict):
                continue
            slot_kind = str(slot.get("kind") or slot.get("slot_kind") or "manifest_slot").strip()
            title = str(slot.get("title") or slot.get("label") or slot_kind).strip()
            summary = str(slot.get("summary") or self._summarize_value(slot.get("value"))).strip()
            if not title or not summary:
                continue
            slot_id = str(slot.get("slot_id") or f"{pack_id}:explicit:{index}").strip()
            slots.append(
                ModelRouteSlot(
                    slot_id=slot_id,
                    owner_kind="pack",
                    owner_id=pack_id,
                    owner_name=owner_name,
                    slot_kind=slot_kind,
                    title=title,
                    summary=summary,
                    route_family=str(slot.get("route_family") or "explicit_manifest").strip(),
                    source="manifest.model_routing.slots",
                    settings_anchor=str(
                        slot.get("settings_anchor") or "basic:model-routing-registry"
                    ).strip(),
                    installed=installed,
                    enabled=enabled,
                    evidence_path=evidence_path,
                    raw=dict(slot),
                )
            )
        return slots

    def _extract_settings_panel_slots(
        self,
        *,
        pack_id: str,
        pack_meta: Dict[str, Any],
        owner_name: str,
        evidence_path: Optional[str],
        installed: bool,
        enabled: bool,
    ) -> List[ModelRouteSlot]:
        slots: List[ModelRouteSlot] = []
        for component in pack_meta.get("ui_components") or []:
            if not isinstance(component, dict):
                continue
            settings = component.get("settings")
            if not isinstance(settings, dict):
                continue
            section = str(settings.get("section") or "").strip()
            if section not in _ROUTE_SETTINGS_PANEL_SECTIONS:
                continue
            title = (
                str(settings.get("title") or component.get("display_name") or component.get("code") or section).strip()
                or section
            )
            scope = "workspace" if settings.get("requires_workspace_id") else "global"
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="settings_panel",
                    title=title,
                    summary=f"section={section}; scope={scope}",
                    route_family="settings_panel",
                    source="manifest.ui_components.settings",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    settings_anchor=f"settings:{section}",
                    raw={
                        "component_code": component.get("code"),
                        "section": section,
                        "requires_workspace_id": bool(settings.get("requires_workspace_id")),
                        "display_mode": settings.get("display_mode"),
                    },
                )
            )
        return slots

    def _build_tool_summary_slots(
        self,
        *,
        pack_id: str,
        owner_name: str,
        tool_route_summary: Dict[str, List[Any]],
        evidence_path: Optional[str],
        installed: bool,
        enabled: bool,
    ) -> List[ModelRouteSlot]:
        slots: List[ModelRouteSlot] = []
        model_usage = tool_route_summary.get("uses_models") or []
        if model_usage:
            examples = [item["code"] for item in model_usage[:4] if item.get("code")]
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="tool_model_usage",
                    title="Tool Model Usage",
                    summary=(
                        f"{len(model_usage)} tools declare model usage"
                        + (f"; examples={', '.join(examples)}" if examples else "")
                    ),
                    route_family="tool_model_usage",
                    source="manifest.tools[*].uses_models",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"tools": model_usage},
                )
            )

        llm_backed_tools = tool_route_summary.get("llm_backed_tools") or []
        if llm_backed_tools:
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="llm_tool_backend",
                    title="LLM-Backed Tools",
                    summary=(
                        f"{len(llm_backed_tools)} tools route through shared LLM surfaces; "
                        f"examples={', '.join(llm_backed_tools[:4])}"
                    ),
                    route_family="llm_tool_backend",
                    source="manifest.tools[*].backend",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"tools": llm_backed_tools},
                )
            )

        provider_overrides = tool_route_summary.get("provider_override_tools") or []
        if provider_overrides:
            slots.append(
                self._build_slot(
                    pack_id=pack_id,
                    owner_name=owner_name,
                    slot_kind="provider_override",
                    title="Provider Override Inputs",
                    summary=(
                        f"{len(provider_overrides)} tools expose provider/model override inputs; "
                        f"examples={', '.join(provider_overrides[:4])}"
                    ),
                    route_family="provider_override",
                    source="manifest.tools[*].input_schema",
                    evidence_path=evidence_path,
                    installed=installed,
                    enabled=enabled,
                    raw={"tools": provider_overrides},
                )
            )

        return slots

    @staticmethod
    def _collect_route_dependency_codes(dependencies: Any) -> List[str]:
        matched: set[str] = set()
        if isinstance(dependencies, list):
            for item in dependencies:
                code = str(item or "").strip()
                if code in _ROUTE_DEPENDENCY_CODES:
                    matched.add(code)
            return sorted(matched)

        if not isinstance(dependencies, dict):
            return []

        for key in ("required", "optional"):
            for item in dependencies.get(key) or []:
                code = ""
                if isinstance(item, str):
                    code = item.strip()
                elif isinstance(item, dict):
                    code = str(item.get("code") or item.get("name") or "").strip()
                if code in _ROUTE_DEPENDENCY_CODES:
                    matched.add(code)

        return sorted(matched)

    @staticmethod
    def _collect_tool_route_summary(tools: Any) -> Dict[str, List[Any]]:
        summary: Dict[str, List[Any]] = {
            "uses_models": [],
            "llm_backed_tools": [],
            "provider_override_tools": [],
        }
        if not isinstance(tools, list):
            return summary

        for tool in tools:
            if not isinstance(tool, dict):
                continue
            code = str(tool.get("code") or tool.get("name") or "").strip()
            uses_models = tool.get("uses_models")
            if isinstance(uses_models, list) and uses_models:
                summary["uses_models"].append(
                    {
                        "code": code,
                        "models": [str(item).strip() for item in uses_models if str(item).strip()],
                    }
                )

            backend = str(tool.get("backend") or "").strip()
            if "core_llm" in backend or "shared_llm" in backend:
                summary["llm_backed_tools"].append(code or backend)

            input_schema = tool.get("input_schema") or {}
            properties = input_schema.get("properties") if isinstance(input_schema, dict) else {}
            if isinstance(properties, dict) and any(
                key in properties for key in ("llm_provider", "model", "model_name")
            ):
                summary["provider_override_tools"].append(code or backend or "tool")

        return {key: value for key, value in summary.items() if value}

    @staticmethod
    def _collect_playbook_route_summary(playbooks: Any) -> List[str]:
        hits: List[str] = []
        if not isinstance(playbooks, list):
            return hits

        for playbook in playbooks:
            if not isinstance(playbook, dict):
                continue
            deps = playbook.get("tool_dependencies") or []
            if not isinstance(deps, list):
                continue
            matched = [
                str(dep).strip()
                for dep in deps
                if isinstance(dep, str)
                and any(
                    dep == code or dep.startswith(f"{code}.")
                    for code in _ROUTE_DEPENDENCY_CODES
                )
            ]
            if matched:
                code = str(playbook.get("code") or playbook.get("display_name") or "playbook").strip()
                hits.append(code)
        return hits

    @staticmethod
    def _normalize_stored_slots(
        stored_slots: Sequence[Any],
        *,
        pack_id: str,
        owner_name: str,
        installed: bool,
        enabled: bool,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, slot in enumerate(stored_slots):
            if not isinstance(slot, dict):
                continue
            normalized.append(
                {
                    "slot_id": str(slot.get("slot_id") or f"{pack_id}:stored:{index}"),
                    "owner_kind": str(slot.get("owner_kind") or "pack"),
                    "owner_id": str(slot.get("owner_id") or pack_id),
                    "owner_name": str(slot.get("owner_name") or owner_name),
                    "slot_kind": str(slot.get("slot_kind") or "stored_slot"),
                    "title": str(slot.get("title") or slot.get("slot_kind") or "stored_slot"),
                    "summary": str(slot.get("summary") or ""),
                    "route_family": str(slot.get("route_family") or "stored_slot"),
                    "source": str(slot.get("source") or "installed_packs.metadata.model_route_slots"),
                    "settings_anchor": str(
                        slot.get("settings_anchor") or "basic:model-routing-registry"
                    ),
                    "installed": slot.get("installed", installed),
                    "enabled": slot.get("enabled", enabled),
                    "evidence_path": slot.get("evidence_path"),
                    "raw": dict(slot.get("raw") or {}),
                }
            )
        return normalized

    @staticmethod
    def _coerce_slot_count(value: Any, *, fallback: int) -> int:
        try:
            if value is None:
                return fallback
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def _pack_slot_registration_changed(
        cls,
        *,
        stored_slots: Sequence[Dict[str, Any]],
        stored_slot_count: Any,
        live_slots: Sequence[Dict[str, Any]],
    ) -> bool:
        normalized_stored_slots = cls._canonicalize_slots(stored_slots)
        normalized_live_slots = cls._canonicalize_slots(live_slots)
        normalized_stored_count = cls._coerce_slot_count(
            stored_slot_count,
            fallback=len(normalized_stored_slots),
        )
        if normalized_stored_count != len(normalized_live_slots):
            return True
        return normalized_stored_slots != normalized_live_slots

    @staticmethod
    def _canonicalize_slots(slots: Sequence[Dict[str, Any]]) -> List[str]:
        canonical: List[str] = []
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            canonical.append(
                json.dumps(slot, sort_keys=True, ensure_ascii=False, default=str)
            )
        return sorted(canonical)

    @staticmethod
    def _summarize_mapping(value: Any) -> str:
        if isinstance(value, dict):
            parts = []
            for key, entry in value.items():
                if isinstance(entry, (dict, list)):
                    parts.append(f"{key}={ModelRouteSlotRegistry._summarize_value(entry)}")
                else:
                    parts.append(f"{key}={entry}")
            return ", ".join(parts[:6])
        return ModelRouteSlotRegistry._summarize_value(value)

    @staticmethod
    def _summarize_value(value: Any) -> str:
        if isinstance(value, dict):
            parts = [f"{key}->{item}" for key, item in list(value.items())[:6]]
            return ", ".join(parts)
        if isinstance(value, list):
            preview = [str(item) for item in value[:6]]
            suffix = "..." if len(value) > 6 else ""
            return ", ".join(preview) + suffix
        return str(value)

    @staticmethod
    def _slug(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return "slot"
        slug = "".join(ch if ch.isalnum() else "_" for ch in text)
        slug = "_".join(part for part in slug.split("_") if part)
        return slug or "slot"

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
        return ModelRouteSlot(
            slot_id=f"{pack_id}:{self._slug(slot_kind)}:{self._slug(title)}",
            owner_kind=owner_kind,
            owner_id=pack_id,
            owner_name=owner_name,
            slot_kind=slot_kind,
            title=title,
            summary=summary,
            route_family=route_family,
            source=source,
            settings_anchor=settings_anchor,
            installed=installed,
            enabled=enabled,
            evidence_path=str(evidence_path) if evidence_path else None,
            raw=dict(raw or {}),
        )
