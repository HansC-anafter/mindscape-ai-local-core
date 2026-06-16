"""
Capability pack manifest model route slot extraction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.services.model_route_slot_schema import (
    _ROUTE_DEPENDENCY_CODES,
    _ROUTE_SETTINGS_PANEL_SECTIONS,
    ModelRouteSlot,
    build_model_route_slot,
    summarize_model_route_mapping,
    summarize_model_route_value,
)


def extract_pack_slots_from_manifest_data(
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
        _extract_explicit_manifest_slots(
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
            build_model_route_slot(
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
        provider_summary = summarize_model_route_mapping(runtime_provider)
        slots.append(
            build_model_route_slot(
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
            build_model_route_slot(
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

    dependency_codes = collect_route_dependency_codes(pack_meta.get("dependencies"))
    if dependency_codes:
        slots.append(
            build_model_route_slot(
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

    tool_route_summary = collect_tool_route_summary(pack_meta.get("tools"))
    if tool_route_summary:
        slots.extend(
            _build_tool_summary_slots(
                pack_id=pack_id,
                owner_name=owner_name,
                tool_route_summary=tool_route_summary,
                evidence_path=evidence_path,
                installed=installed,
                enabled=enabled,
            )
        )

    playbook_summary = collect_playbook_route_summary(pack_meta.get("playbooks"))
    if playbook_summary:
        slots.append(
            build_model_route_slot(
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
        _extract_settings_panel_slots(
            pack_id=pack_id,
            pack_meta=pack_meta,
            owner_name=owner_name,
            evidence_path=evidence_path,
            installed=installed,
            enabled=enabled,
        )
    )

    return [slot.to_dict() for slot in slots]


def _extract_explicit_manifest_slots(
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
        slot_kind = str(
            slot.get("kind") or slot.get("slot_kind") or "manifest_slot"
        ).strip()
        title = str(slot.get("title") or slot.get("label") or slot_kind).strip()
        summary = str(
            slot.get("summary") or summarize_model_route_value(slot.get("value"))
        ).strip()
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
                route_family=str(
                    slot.get("route_family") or "explicit_manifest"
                ).strip(),
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
            str(
                settings.get("title")
                or component.get("display_name")
                or component.get("code")
                or section
            ).strip()
            or section
        )
        scope = "workspace" if settings.get("requires_workspace_id") else "global"
        slots.append(
            build_model_route_slot(
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
                    "requires_workspace_id": bool(
                        settings.get("requires_workspace_id")
                    ),
                    "display_mode": settings.get("display_mode"),
                },
            )
        )
    return slots


def _build_tool_summary_slots(
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
            build_model_route_slot(
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
            build_model_route_slot(
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
            build_model_route_slot(
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


def collect_route_dependency_codes(dependencies: Any) -> List[str]:
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


def collect_tool_route_summary(tools: Any) -> Dict[str, List[Any]]:
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
                    "models": [
                        str(item).strip() for item in uses_models if str(item).strip()
                    ],
                }
            )

        backend = str(tool.get("backend") or "").strip()
        if "core_llm" in backend or "shared_llm" in backend:
            summary["llm_backed_tools"].append(code or backend)

        input_schema = tool.get("input_schema") or {}
        properties = (
            input_schema.get("properties") if isinstance(input_schema, dict) else {}
        )
        if isinstance(properties, dict) and any(
            key in properties for key in ("llm_provider", "model", "model_name")
        ):
            summary["provider_override_tools"].append(code or backend or "tool")

    return {key: value for key, value in summary.items() if value}


def collect_playbook_route_summary(playbooks: Any) -> List[str]:
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
            code = str(
                playbook.get("code") or playbook.get("display_name") or "playbook"
            ).strip()
            hits.append(code)
    return hits
