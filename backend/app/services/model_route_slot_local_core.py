"""
Local-core model route slot collection.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.app.services.model_route_slot_schema import (
    _SYSTEM_SETTING_SLOTS,
    build_model_route_slot,
    summarize_model_route_value,
)


def collect_local_core_model_route_slots(
    system_settings_store: Any,
) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    for key, title, slot_kind, settings_anchor in _SYSTEM_SETTING_SLOTS:
        setting = system_settings_store.get_setting(key)
        if setting is None:
            continue
        if setting.value in (None, "", {}, []):
            continue
        slots.append(
            build_model_route_slot(
                pack_id="local-core",
                owner_name="Local-Core",
                slot_kind=slot_kind,
                title=title,
                summary=summarize_model_route_value(setting.value),
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

    capability_profile_mapping = system_settings_store.get_capability_profile_mapping()
    if capability_profile_mapping:
        slots.append(
            build_model_route_slot(
                pack_id="local-core",
                owner_name="Local-Core",
                slot_kind="capability_profile_mapping",
                title="Stage to Capability Profile Mapping",
                summary=summarize_model_route_value(capability_profile_mapping),
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

    from backend.app.services.executor_routing_policy_service import (
        ExecutorRoutingPolicyService,
    )
    from backend.app.services.model_routing_policy_service import (
        ModelRoutingPolicyService,
    )

    local_profile_bindings = ModelRoutingPolicyService(
        settings_store=system_settings_store
    ).get_profile_bindings_for_scope("local")
    if local_profile_bindings:
        slots.append(
            build_model_route_slot(
                pack_id="local-core",
                owner_name="Local-Core",
                slot_kind="profile_model_bindings_local",
                title="Local Scoped Profile Bindings",
                summary=summarize_model_route_value(local_profile_bindings),
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

    profile_model_bindings = system_settings_store.get_profile_model_bindings()
    if profile_model_bindings:
        slots.append(
            build_model_route_slot(
                pack_id="local-core",
                owner_name="Local-Core",
                slot_kind="profile_model_bindings",
                title="Scoped Profile Model Bindings",
                summary=summarize_model_route_value(profile_model_bindings),
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
        build_model_route_slot(
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
        build_model_route_slot(
            pack_id="local-core",
            owner_name="Local-Core",
            slot_kind="runtime_substitution_policy",
            title="Runtime Substitution Policy",
            summary=summarize_model_route_value(
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
