"""
Capability Profile System

Manages capability profiles (fast/standard/precise/tool_strict/safe_write) and model selection
for staged model switching optimization.
"""

import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class CapabilityProfile(str, Enum):
    """Capability profile enumeration"""
    FAST = "fast"
    STANDARD = "standard"
    PRECISE = "precise"
    TOOL_STRICT = "tool_strict"
    SAFE_WRITE = "safe_write"
    LONG_CONTEXT = "long_context"


@dataclass
class ProfileConfig:
    """Capability profile configuration"""
    profile: CapabilityProfile
    model_candidates: List[str]  # Candidate model list (ordered by priority)
    required_capabilities: List[str]  # Required capabilities
    max_latency_ms: int
    max_cost_per_1k_tokens: float
    fallback_profile: Optional[CapabilityProfile] = None


class CapabilityProfileRegistry:
    """Capability profile registry and model selector"""

    def __init__(self):
        # Default profile configurations
        # Note: model_candidates are examples, actual should support multiple providers
        # Can be overridden by SystemSettingsStore profile_model_mapping
        self.profiles: Dict[CapabilityProfile, ProfileConfig] = {
            CapabilityProfile.FAST: ProfileConfig(
                profile=CapabilityProfile.FAST,
                model_candidates=["gpt-3.5-turbo", "gpt-4o-mini", "claude-3-haiku", "gemini-1.5-flash"],
                required_capabilities=["json_strict"],
                max_latency_ms=1000,
                max_cost_per_1k_tokens=0.002,
                fallback_profile=CapabilityProfile.STANDARD
            ),
            CapabilityProfile.STANDARD: ProfileConfig(
                profile=CapabilityProfile.STANDARD,
                model_candidates=["gpt-4o", "gpt-4-turbo", "claude-3-sonnet", "gemini-1.5-pro"],
                required_capabilities=["json_strict", "tool_calling"],
                max_latency_ms=3000,
                max_cost_per_1k_tokens=0.01,
                fallback_profile=CapabilityProfile.FAST
            ),
            CapabilityProfile.PRECISE: ProfileConfig(
                profile=CapabilityProfile.PRECISE,
                model_candidates=["gpt-4", "gpt-4-turbo", "claude-3-opus", "gemini-2.0-pro"],
                required_capabilities=["strong_reasoning", "json_strict"],
                max_latency_ms=8000,
                max_cost_per_1k_tokens=0.03,
                fallback_profile=CapabilityProfile.STANDARD
            ),
            CapabilityProfile.TOOL_STRICT: ProfileConfig(
                profile=CapabilityProfile.TOOL_STRICT,
                model_candidates=["gpt-4", "gpt-4-turbo", "claude-3-opus"],
                required_capabilities=["json_strict", "tool_calling", "schema_validation"],
                max_latency_ms=5000,
                max_cost_per_1k_tokens=0.03,
                fallback_profile=CapabilityProfile.STANDARD
            ),
            CapabilityProfile.SAFE_WRITE: ProfileConfig(
                profile=CapabilityProfile.SAFE_WRITE,
                model_candidates=["gpt-4", "gpt-4-turbo", "claude-3-opus"],
                required_capabilities=["strong_reasoning", "conservative_scope"],
                max_latency_ms=8000,
                max_cost_per_1k_tokens=0.03,
                fallback_profile=CapabilityProfile.STANDARD
            ),
        }

    def get_profile(self, profile: CapabilityProfile) -> ProfileConfig:
        """
        Get profile configuration

        Args:
            profile: Capability profile

        Returns:
            ProfileConfig instance
        """
        return self.profiles.get(profile, self.profiles[CapabilityProfile.STANDARD])

    def select_model(
        self,
        profile: CapabilityProfile,
        llm_provider_manager: Any,
        profile_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Select appropriate model for capability profile

        Args:
            profile: Capability profile
            llm_provider_manager: LLM Provider Manager instance (for checking provider availability)
            profile_id: Profile ID (for reading tenant-specific model mappings)

        Returns:
            Model name, or None if no available model (will trigger fallback to chat_model)
        """
        # Check feature flag
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        enable_flag = settings_store.get_setting("enable_capability_profile")

        if not enable_flag or str(enable_flag.value).lower() != "true":
            logger.debug("Capability profile system is disabled, will fallback to chat_model")
            return None

        config = self.get_profile(profile)

        # Prioritize tenant-specific model mappings (if profile_id provided)
        custom_models = self._get_custom_model_mapping(profile_id, profile)
        if custom_models:
            model_candidates = custom_models + config.model_candidates
        else:
            model_candidates = config.model_candidates

        # Override with SystemSettingsStore profile_model_mapping if available
        profile_mapping = settings_store.get_profile_model_mapping()
        if profile_mapping and profile.value in profile_mapping:
            # Prepend custom models to the list
            custom_models_from_settings = profile_mapping[profile.value]
            model_candidates = custom_models_from_settings + [
                m for m in model_candidates if m not in custom_models_from_settings
            ]

        # Iterate through candidate models and check availability
        for model_name in model_candidates:
            # Resolve provider for model (prioritize config, then infer from model name)
            provider_name = self._resolve_provider_for_model(
                model_name=model_name,
                profile_id=profile_id,
                llm_provider_manager=llm_provider_manager
            )
            if not provider_name:
                logger.debug(
                    f"Cannot resolve provider for model {model_name}, "
                    f"trying next candidate (custom model requires provider mapping)"
                )
                continue

            # Check provider availability (using real LLMProviderManager API)
            try:
                provider = llm_provider_manager.get_provider(provider_name)
                if not provider:
                    logger.debug(f"Provider {provider_name} not available, trying next candidate")
                    continue
            except ValueError as e:
                logger.debug(f"Provider {provider_name} not available (ValueError): {e}")
                continue
            except Exception as e:
                logger.debug(f"Provider {provider_name} not available (Exception): {e}")
                continue

            # Check model support
            if self._is_model_supported(provider, model_name):
                logger.debug(f"Selected model {model_name} from provider {provider_name}")
                return model_name
            else:
                logger.debug(
                    f"Model {model_name} not supported by provider {provider_name}, trying next candidate"
                )

        # If all candidates failed, try fallback_profile
        if config.fallback_profile:
            logger.debug(
                f"All candidates failed for profile {profile.value}, "
                f"trying fallback_profile {config.fallback_profile.value}"
            )
            return self.select_model(config.fallback_profile, llm_provider_manager, profile_id=profile_id)

        # If fallback also failed, return None (will trigger chat_model fallback)
        logger.warning(
            f"All model selection methods failed for profile {profile.value}, will fallback to chat_model"
        )
        return None

    def _get_custom_model_mapping(
        self,
        profile_id: Optional[str],
        profile: CapabilityProfile
    ) -> Optional[List[str]]:
        """
        Get tenant-specific model mapping

        Reads from SystemSettingsStore or ConfigStore for tenant-specific model lists.

        Args:
            profile_id: Profile ID (for reading tenant-specific config)
            profile: Capability profile

        Returns:
            Tenant-specific model list or None
        """
        try:
            # Method 1: Read from SystemSettingsStore global config
            from backend.app.services.system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore()
            profile_mapping = settings_store.get_profile_model_mapping()

            if profile_mapping and profile.value in profile_mapping:
                custom_models = profile_mapping[profile.value]
                # Filter out standard models, return only custom models
                standard_prefixes = ["gpt", "claude", "gemini", "text-", "o1"]
                custom_only = [
                    model for model in custom_models
                    if not any(model.lower().startswith(prefix) for prefix in standard_prefixes)
                ]
                if custom_only:
                    logger.debug(f"Found {len(custom_only)} custom models for profile {profile.value}")
                    return custom_only

            # Method 2: Read from ConfigStore tenant-specific config (if profile_id provided)
            if profile_id:
                try:
                    from backend.app.services.config_store import ConfigStore
                    config_store = ConfigStore()
                    config = config_store.get_or_create_config(profile_id)

                    # Read from metadata.profile_model_mapping if exists
                    if config.metadata:
                        metadata = config.metadata if isinstance(config.metadata, dict) else json.loads(config.metadata) if isinstance(config.metadata, str) else {}
                        profile_mapping = metadata.get("profile_model_mapping", {})
                        if profile_mapping and profile.value in profile_mapping:
                            custom_models = profile_mapping[profile.value]
                            # Filter out standard models, return only custom models
                            standard_prefixes = ["gpt", "claude", "gemini", "text-", "o1"]
                            custom_only = [
                                model for model in custom_models
                                if not any(model.lower().startswith(prefix) for prefix in standard_prefixes)
                            ]
                            if custom_only:
                                logger.debug(f"Found {len(custom_only)} tenant-specific custom models for profile {profile.value}")
                                return custom_only
                except Exception as e:
                    logger.debug(f"Failed to read tenant-specific profile_model_mapping: {e}")

            return None
        except Exception as e:
            logger.debug(f"Failed to get custom model mapping: {e}")
            return None

    def _resolve_provider_for_model(
        self,
        model_name: str,
        profile_id: Optional[str],
        llm_provider_manager: Any
    ) -> Optional[str]:
        """
        Resolve provider for model name

        Priority:
        1) SystemSettingsStore custom_model_provider_mapping
        2) ConfigStore (tenant-specific) custom_model_provider_mapping
        3) Infer from model name (_infer_provider_from_model)

        Args:
            model_name: Model name
            profile_id: Profile ID (for reading tenant-specific config)
            llm_provider_manager: LLM Provider Manager instance

        Returns:
            Provider name ("openai", "anthropic", "vertex-ai") or None
        """
        if not model_name:
            return None

        # 1) Read from SystemSettingsStore custom_model_provider_mapping
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore()
            provider_mapping = settings_store.get_custom_model_provider_mapping()
            if provider_mapping and model_name in provider_mapping:
                return provider_mapping[model_name]
        except Exception as e:
            logger.debug(f"Failed to read custom_model_provider_mapping from settings: {e}")

        # 2) Read from ConfigStore (tenant-specific)
        if profile_id:
            try:
                from backend.app.services.config_store import ConfigStore
                import json
                config_store = ConfigStore()
                config = config_store.get_or_create_config(profile_id)

                # Read from metadata.custom_model_provider_mapping if exists
                if config.metadata:
                    metadata = config.metadata if isinstance(config.metadata, dict) else json.loads(config.metadata) if isinstance(config.metadata, str) else {}
                    provider_mapping = metadata.get("custom_model_provider_mapping", {})
                    if provider_mapping and model_name in provider_mapping:
                        logger.debug(f"Found tenant-specific provider mapping for {model_name}: {provider_mapping[model_name]}")
                        return provider_mapping[model_name]
            except Exception as e:
                logger.debug(f"Failed to read custom_model_provider_mapping from tenant config: {e}")

        # 3) Infer from model name
        return self._infer_provider_from_model(model_name)

    def _infer_provider_from_model(self, model_name: str) -> Optional[str]:
        """
        Infer provider from model name

        Args:
            model_name: Model name

        Returns:
            Provider name ("openai", "anthropic", "vertex-ai") or None
        """
        if not model_name:
            return None

        model_lower = model_name.lower()

        # OpenAI models: gpt-*, text-*, o1-*
        if "gpt" in model_lower or "text-" in model_lower or "o1" in model_lower:
            return "openai"

        # Anthropic models: claude-*
        elif "claude" in model_lower:
            return "anthropic"

        # Vertex AI models: gemini-*
        elif "gemini" in model_lower:
            return "vertex-ai"

        else:
            # For tenant custom model names/aliases, need to read from config
            logger.debug(f"Cannot infer provider from model name: {model_name}, may be a custom model")
            return None

    def _is_model_supported(self, provider: Any, model_name: str) -> bool:
        """
        Check if model is supported by provider

        Note: Real LLMProviderManager doesn't have is_model_available method.
        We check through:
        1. provider.supported_models (if exists)
        2. provider._model_instance_cache (if exists)
        3. Provider internal interface (if available) - PRIORITY for custom model names
        4. Provider type inference (for standard models)
        5. Default to False for unknown providers (conservative approach)

        Args:
            provider: Provider instance
            model_name: Model name

        Returns:
            True if model is supported, False otherwise
        """
        # Method 1: Check provider.supported_models (if exists)
        if hasattr(provider, 'supported_models') and provider.supported_models:
            return model_name in provider.supported_models

        # Method 2: Check provider._model_instance_cache (if exists)
        if hasattr(provider, '_model_instance_cache'):
            cache_key = f"{provider.__class__.__name__}:{model_name}"
            if cache_key in provider._model_instance_cache:
                return True

        # Method 3: Try provider internal interface FIRST (before prefix inference)
        # This allows custom model names that don't match standard prefixes
        if hasattr(provider, 'is_model_available'):
            try:
                result = provider.is_model_available(model_name)
                if result is not None:
                    return result
            except Exception as e:
                logger.debug(f"Provider.is_model_available() failed for {model_name}: {e}")

        # Method 4: Check if provider has list_models
        if hasattr(provider, 'list_models'):
            try:
                available_models = provider.list_models()
                if available_models and model_name in available_models:
                    return True
            except Exception as e:
                logger.debug(f"Provider.list_models() failed: {e}")

        # Method 5: For known standard models, infer from provider type
        # This is a fallback for standard models (gpt-*, claude-*, gemini-*)
        provider_type = provider.__class__.__name__
        if provider_type == "OpenAIProvider":
            return "gpt" in model_name.lower() or "text-" in model_name.lower() or "o1" in model_name.lower()
        elif provider_type == "AnthropicProvider":
            return "claude" in model_name.lower()
        elif provider_type == "VertexAIProvider":
            return "gemini" in model_name.lower()

        # Method 6: For unknown provider types, default to False (conservative)
        # This prevents selecting models that might not be supported
        # Will fallback to chat_model or fallback_profile if this returns False
        logger.warning(
            f"Cannot determine if model {model_name} is supported by provider {provider_type}. "
            f"Defaulting to False (conservative). Will try fallback_profile or chat_model."
        )
        return False

