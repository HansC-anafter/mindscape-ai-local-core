"""Capability profile and model binding helpers for SystemSettingsStore."""

import json
from typing import Any, Dict, Optional

from backend.app.models.system_settings import SettingType


class SystemSettingsProfileBindingsMixin:
    def set_capability_profile_mapping(self, mapping: Dict[str, str]) -> None:
        self.set_setting(
            key="capability_profile_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Stage to capability profile mapping for staged model switching",
        )

    def get_capability_profile_mapping(self) -> Dict[str, str]:
        setting = self.get_setting("capability_profile_mapping")
        if setting and isinstance(setting.value, dict):
            return setting.value
        return {}

    @staticmethod
    def _normalize_profile_bindings_entry(
        mapping: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        if not isinstance(mapping, dict):
            return normalized
        for key, value in mapping.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            normalized[key.strip()] = value.strip()
        return normalized

    @staticmethod
    def _normalize_profile_model_bindings(
        bindings: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, str]]:
        normalized: Dict[str, Dict[str, str]] = {}
        if not isinstance(bindings, dict):
            return normalized
        for scope, mapping in bindings.items():
            if not isinstance(scope, str) or not scope.strip():
                continue
            from backend.app.services.system_settings_store import SystemSettingsStore

            normalized[scope.strip()] = (
                SystemSettingsStore._normalize_profile_bindings_entry(mapping)
            )
        return normalized

    def _load_profile_model_bindings_setting(self) -> Dict[str, Dict[str, str]]:
        setting = self.get_setting("profile_model_bindings")
        if setting:
            if isinstance(setting.value, dict):
                return self._normalize_profile_model_bindings(setting.value)
            if isinstance(setting.value, str):
                try:
                    parsed = json.loads(setting.value)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    return self._normalize_profile_model_bindings(parsed)
        return {}

    def set_local_profile_model_bindings(self, bindings: Dict[str, str]) -> None:
        normalized_entry = self._normalize_profile_bindings_entry(bindings)
        normalized_bindings = self._load_profile_model_bindings_setting()
        normalized_bindings["local"] = normalized_entry
        normalized_bindings.setdefault("cloud", {})
        self.set_setting(
            key="profile_model_bindings",
            value=normalized_bindings,
            value_type=SettingType.JSON,
            category="llm",
            description="Deployment-scoped capability profile to model bindings",
        )

    def get_local_profile_model_bindings(self) -> Dict[str, str]:
        bindings = self._load_profile_model_bindings_setting()
        local_binding = bindings.get("local")
        if isinstance(local_binding, dict):
            return local_binding
        return {}

    def set_profile_model_bindings(self, bindings: Dict[str, Dict[str, str]]) -> None:
        normalized = self._normalize_profile_model_bindings(bindings)
        if "local" not in normalized:
            normalized["local"] = {}
        if "cloud" not in normalized:
            normalized["cloud"] = {}

        self.set_setting(
            key="profile_model_bindings",
            value=normalized,
            value_type=SettingType.JSON,
            category="llm",
            description="Deployment-scoped capability profile to model bindings",
        )

    def get_profile_model_bindings(self) -> Dict[str, Dict[str, str]]:
        bindings = self._load_profile_model_bindings_setting()
        if bindings:
            bindings.setdefault("local", {})
            bindings.setdefault("cloud", {})
            return bindings
        return {"local": {}, "cloud": {}}

    def get_profile_model_bindings_for_scope(self, scope: str = "local") -> Dict[str, str]:
        bindings = self.get_profile_model_bindings()
        mapping = bindings.get(scope)
        if isinstance(mapping, dict):
            return mapping
        return {}

    def set_custom_model_provider_mapping(self, mapping: Dict[str, str]) -> None:
        self.set_setting(
            key="custom_model_provider_mapping",
            value=mapping,
            value_type=SettingType.JSON,
            category="llm",
            description="Custom model name to provider mapping for tenant-specific models",
        )

    def get_custom_model_provider_mapping(self) -> Dict[str, str]:
        setting = self.get_setting("custom_model_provider_mapping")
        if setting:
            if isinstance(setting.value, dict):
                return setting.value
            if isinstance(setting.value, str):
                try:
                    return json.loads(setting.value)
                except json.JSONDecodeError:
                    return {}
        return {}
