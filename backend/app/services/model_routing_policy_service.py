"""Single-source helpers for model-routing-registry-backed policy and surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.app.models.model_provider import ModelType as ProviderModelType
from backend.app.models.system_settings import (
    LLMModelConfig,
    ModelType,
    SettingType,
    SystemSetting,
)
from backend.app.services.model_config_store import ModelConfigStore
from backend.app.services.system_settings_store import SystemSettingsStore


@dataclass(frozen=True)
class ResolvedChatRoute:
    model_name: Optional[str]
    provider: Optional[str]
    source: str
    route_authority: str = "model-routing-registry"
    workspace_override_active: bool = False
    fallback_allowed: bool = False


class ModelRoutingPolicyService:
    """Central policy contract for model-routing-registry-backed model resolution."""

    def __init__(
        self,
        *,
        settings_store: Optional[SystemSettingsStore] = None,
        model_config_store: Optional[ModelConfigStore] = None,
    ) -> None:
        self._settings_store = settings_store or SystemSettingsStore()
        self._model_config_store = model_config_store or ModelConfigStore()

    def build_policy_summary(self) -> Dict[str, Any]:
        return {
            "route_authority": "model-routing-registry",
            "precedence": [
                {
                    "key": "global_registry",
                    "label": "Global registry default",
                    "summary": (
                        "Local-Core model-routing-registry system settings are the "
                        "authoritative source for chat_model and profile_model_bindings."
                    ),
                    "active": True,
                },
                {
                    "key": "workspace_override",
                    "label": "Workspace override",
                    "summary": (
                        "Workspace-level model override is not enabled for workspace "
                        "chat / executor / meeting surfaces in this release."
                    ),
                    "active": False,
                },
            ],
            "workspace_override": {
                "enabled": False,
                "summary": (
                    "Workspace surfaces currently inherit the global registry. "
                    "No separate workspace model override is active."
                ),
            },
            "fallback_policy": {
                "allowed": False,
                "mode": "fail_closed",
                "summary": (
                    "Model routing defaults to fail-closed. Workspace chat, meeting, "
                    "and executor surfaces must not silently rebind to another model "
                    "or runtime outside the registry-backed contract."
                ),
            },
            "surfaces": [
                {
                    "surface": "workspace_chat",
                    "model_source": "system_settings.chat_model",
                    "workspace_override_enabled": False,
                    "fallback_allowed": False,
                },
                {
                    "surface": "meeting_generation",
                    "model_source": "system_settings.chat_model + profile_model_bindings",
                    "workspace_override_enabled": False,
                    "fallback_allowed": False,
                },
                {
                    "surface": "executor_conversation",
                    "model_source": "system_settings.chat_model + profile_model_bindings",
                    "workspace_override_enabled": False,
                    "fallback_allowed": False,
                },
            ],
        }

    def resolve_chat_default(
        self,
        *,
        default: Optional[str] = None,
    ) -> ResolvedChatRoute:
        chat_setting = self._settings_store.get_setting("chat_model")
        provider_setting = self._settings_store.get_setting("default_llm_provider")
        default_provider = (
            str(provider_setting.value).strip()
            if provider_setting and provider_setting.value not in (None, "")
            else "openai"
        )

        if chat_setting and chat_setting.value not in (None, ""):
            metadata = getattr(chat_setting, "metadata", None) or {}
            provider = str(metadata.get("provider") or default_provider).strip()
            return ResolvedChatRoute(
                model_name=str(chat_setting.value).strip(),
                provider=provider or None,
                source="system_settings.chat_model",
            )

        if default:
            return ResolvedChatRoute(
                model_name=default,
                provider=default_provider or None,
                source="default.chat_model",
            )

        return ResolvedChatRoute(
            model_name=None,
            provider=default_provider or None,
            source="system_settings.chat_model",
        )

    def get_profile_bindings_for_scope(self, scope: str = "local") -> Dict[str, str]:
        normalized_scope = str(scope or "local").strip() or "local"
        return self._settings_store.get_profile_model_bindings_for_scope(normalized_scope)

    def list_available_chat_models(self) -> List[Dict[str, Any]]:
        enabled_models = self._model_config_store.get_all_models(
            model_type=ProviderModelType.CHAT,
            enabled=True,
        )
        if enabled_models:
            return [
                {
                    "model_name": model.model_name,
                    "provider": model.provider_name,
                    "description": model.description or "",
                }
                for model in enabled_models
            ]
        from backend.app.routes.core.system_settings.constants import (
            DEFAULT_CHAT_MODELS,
        )

        return DEFAULT_CHAT_MODELS

    def build_workspace_chat_payload(
        self,
        *,
        workspace_id: Optional[str] = None,
        profile_id: str = "default-user",
    ) -> Dict[str, Any]:
        resolved = self.resolve_chat_default()
        chat_model = None
        if resolved.model_name:
            chat_model = LLMModelConfig(
                model_name=resolved.model_name,
                provider=resolved.provider or "openai",
                model_type=ModelType.CHAT,
                metadata={
                    "source": resolved.source,
                    "route_authority": resolved.route_authority,
                },
            )

        return {
            "workspace_id": workspace_id,
            "profile_id": profile_id,
            "route_authority": resolved.route_authority,
            "workspace_override_active": resolved.workspace_override_active,
            "fallback_allowed": resolved.fallback_allowed,
            "dispatch_chain": [resolved.route_authority, resolved.source],
            "source": resolved.source,
            "chat_model": chat_model,
            "available_chat_models": self.list_available_chat_models(),
            "policy": self.build_policy_summary(),
        }

    def update_chat_default(
        self,
        *,
        model_name: str,
        provider: str = "openai",
        api_key_setting_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "provider": provider,
            "model_type": "chat",
            "route_authority": "model-routing-registry",
        }
        if api_key_setting_key:
            metadata["api_key_setting_key"] = api_key_setting_key

        setting = SystemSetting(
            key="chat_model",
            value=model_name,
            value_type=SettingType.STRING,
            category="llm",
            description="Model for chat/conversation inference",
            is_sensitive=False,
            is_user_editable=True,
            metadata=metadata,
        )
        self._settings_store.save_setting(setting)
        return self.build_workspace_chat_payload()
