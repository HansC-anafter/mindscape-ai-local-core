"""Single-source helpers for model-routing-registry-backed policy and surfaces."""

from __future__ import annotations

import os
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


@dataclass(frozen=True)
class ResolvedProfileModelRoute:
    profile: str
    scope: str
    model_name: Optional[str]
    provider: Optional[str]
    source: str
    metadata: Dict[str, Any]
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
                    "model_source": "model-routing-registry.chat_model",
                    "workspace_override_enabled": False,
                    "fallback_allowed": False,
                },
                {
                    "surface": "meeting_generation",
                    "model_source": "model-routing-registry.chat_model + profile_model_bindings",
                    "workspace_override_enabled": False,
                    "fallback_allowed": False,
                },
                {
                    "surface": "executor_conversation",
                    "model_source": "model-routing-registry.chat_model + profile_model_bindings",
                    "workspace_override_enabled": False,
                    "fallback_allowed": False,
                },
            ],
        }

    def resolve_chat_default(self) -> ResolvedChatRoute:
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

        return ResolvedChatRoute(
            model_name=None,
            provider=default_provider or None,
            source="system_settings.chat_model",
        )

    def get_profile_bindings_for_scope(self, scope: str = "local") -> Dict[str, str]:
        normalized_scope = str(scope or "local").strip() or "local"
        return self._settings_store.get_profile_model_bindings_for_scope(normalized_scope)

    @staticmethod
    def _resolve_host_resource_env_profile_model(
        *,
        profile: str,
        scope: str,
    ) -> Optional[ResolvedProfileModelRoute]:
        """Resolve an explicit host-resource worker model binding."""

        normalized_profile = str(profile or "").strip()
        normalized_scope = str(scope or "local").strip() or "local"
        if normalized_scope != "local" or normalized_profile != "vision":
            return None

        adapter_id = str(os.getenv("LOCAL_CORE_RUNTIME_ADAPTER_ID") or "").strip()
        if adapter_id != "apple_mlx_vlm":
            return None

        model_name = (
            str(os.getenv("MLX_MODEL") or "").strip()
            or str(os.getenv("LOCAL_CORE_RUNTIME_MODEL") or "").strip()
        )
        if not model_name:
            return None

        endpoint = (
            str(os.getenv("LOCAL_CORE_RUNTIME_ENDPOINT") or "").strip()
            or str(os.getenv("MLX_BASE_URL") or "").strip()
        )
        port = str(os.getenv("MLX_PORT") or "").strip()
        if not endpoint and port:
            endpoint = f"http://host.docker.internal:{port}"
        if not endpoint:
            return None

        metadata = {
            "runtime_provider": "mlx",
            "base_url": endpoint.rstrip("/"),
            "host_resource_adapter_id": adapter_id,
            "host_resource_runtime_environment_id": str(
                os.getenv("LOCAL_CORE_RUNTIME_ENVIRONMENT_ID") or ""
            ).strip(),
            "host_resource_lane_id": str(
                os.getenv("LOCAL_CORE_HOST_RESOURCE_LANE_ID")
                or os.getenv("LOCAL_CORE_RUNNER_PROFILE")
                or ""
            ).strip(),
            "route_authority": "host-resource-runtime-env",
        }
        max_tokens = str(os.getenv("LOCAL_CORE_RUNTIME_MAX_OUTPUT_TOKENS") or "").strip()
        if max_tokens:
            metadata["local_max_output_tokens_cap"] = max_tokens

        return ResolvedProfileModelRoute(
            profile=normalized_profile,
            scope=normalized_scope,
            model_name=model_name,
            provider="mlx",
            source="host_resource_runtime_env.local.vision",
            metadata={key: value for key, value in metadata.items() if value},
        )

    def _find_enabled_model_config(
        self,
        *,
        model_name: str,
        model_type: Optional[ProviderModelType] = None,
    ) -> Optional[Any]:
        if not model_name:
            return None
        enabled_models = self._model_config_store.get_all_models(
            model_type=model_type,
            enabled=True,
        )
        for model in enabled_models:
            if getattr(model, "model_name", None) == model_name:
                return model
        return None

    @staticmethod
    def _resolve_runtime_provider(
        *,
        provider: Optional[str],
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        """Return the runtime provider declared by the registry metadata.

        `provider_name` can describe where the model came from, e.g. a
        HuggingFace model card. Local multimodal execution still needs the
        concrete runtime provider, e.g. the MLX OpenAI-compatible endpoint.
        """
        normalized_provider = str(provider or "").strip() or None
        runtime_provider = str(
            metadata.get("runtime_provider")
            or metadata.get("runtime_engine")
            or metadata.get("inference_provider")
            or ""
        ).strip()
        if runtime_provider and runtime_provider != "auto":
            return runtime_provider

        hf_format = str(metadata.get("hf_format") or "").strip().lower()
        hf_tags = [
            str(tag or "").strip().lower()
            for tag in (metadata.get("hf_tags") or [])
            if str(tag or "").strip()
        ]
        if normalized_provider == "huggingface" and (
            hf_format == "mlx" or "mlx" in hf_tags
        ):
            return "mlx"

        return normalized_provider

    def resolve_registered_model(
        self,
        *,
        model_name: str,
        model_type: Optional[ProviderModelType] = None,
        source: str = "requested_model",
    ) -> ResolvedProfileModelRoute:
        normalized_model_name = str(model_name or "").strip()
        if not normalized_model_name:
            return ResolvedProfileModelRoute(
                profile="",
                scope="local",
                model_name=None,
                provider=None,
                source=source,
                metadata={},
            )

        model_config = self._find_enabled_model_config(
            model_name=normalized_model_name,
            model_type=model_type,
        )
        if model_config is None:
            expected_type = (
                getattr(model_type, "value", str(model_type))
                if model_type is not None
                else "enabled"
            )
            raise ValueError(
                f"Model '{normalized_model_name}' from {source} is not registered "
                f"as an enabled {expected_type} model in model-routing-registry."
            )

        metadata = dict(getattr(model_config, "metadata", None) or {})
        provider = self._resolve_runtime_provider(
            provider=str(getattr(model_config, "provider_name", "") or "").strip(),
            metadata=metadata,
        )
        if not provider:
            raise ValueError(
                f"Model '{normalized_model_name}' from {source} has no configured "
                "provider in model-routing-registry."
            )

        return ResolvedProfileModelRoute(
            profile="",
            scope="local",
            model_name=normalized_model_name,
            provider=provider,
            source=source,
            metadata=metadata,
        )

    def resolve_profile_model(
        self,
        *,
        profile: str,
        scope: str = "local",
        model_type: Optional[ProviderModelType] = None,
    ) -> ResolvedProfileModelRoute:
        normalized_profile = str(profile or "").strip()
        normalized_scope = str(scope or "local").strip() or "local"
        host_resource_route = self._resolve_host_resource_env_profile_model(
            profile=normalized_profile,
            scope=normalized_scope,
        )
        if host_resource_route is not None:
            return host_resource_route

        source = (
            f"system_settings.profile_model_bindings."
            f"{normalized_scope}.{normalized_profile or '<unset>'}"
        )
        if not normalized_profile:
            return ResolvedProfileModelRoute(
                profile="",
                scope=normalized_scope,
                model_name=None,
                provider=None,
                source=source,
                metadata={},
            )

        bindings = self.get_profile_bindings_for_scope(normalized_scope)
        model_name = str(bindings.get(normalized_profile) or "").strip() or None
        if not model_name:
            return ResolvedProfileModelRoute(
                profile=normalized_profile,
                scope=normalized_scope,
                model_name=None,
                provider=None,
                source=source,
                metadata={},
            )

        route = self.resolve_registered_model(
            model_name=model_name,
            model_type=model_type,
            source=source,
        )
        return ResolvedProfileModelRoute(
            profile=normalized_profile,
            scope=normalized_scope,
            model_name=route.model_name,
            provider=route.provider,
            source=source,
            metadata=route.metadata,
        )

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
