"""
Model Utility Configuration Store

Stores and manages utility function configurations for models (cost, success rate, etc.)
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import json

from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.models.system_settings import SystemSetting, SettingType

logger = logging.getLogger(__name__)


@dataclass
class ModelUtilityConfig:
    """Model utility configuration"""
    model_name: str
    provider: str
    cost_per_1m_tokens: float  # Cost per 1M tokens
    success_rate: float  # Expected success rate (0-1)
    latency_ms: Optional[int] = None  # Average latency in milliseconds
    enabled: bool = True
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "model_name": self.model_name,
            "provider": self.provider,
            "cost_per_1m_tokens": self.cost_per_1m_tokens,
            "success_rate": self.success_rate,
            "enabled": self.enabled,
        }
        if self.latency_ms is not None:
            result["latency_ms"] = self.latency_ms
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelUtilityConfig":
        """Create from dictionary"""
        return cls(
            model_name=data["model_name"],
            provider=data["provider"],
            cost_per_1m_tokens=data["cost_per_1m_tokens"],
            success_rate=data["success_rate"],
            latency_ms=data.get("latency_ms"),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata"),
        )


class ModelUtilityConfigStore:
    """
    Store for model utility configurations

    Manages utility function parameters for each model (cost, success rate, etc.)
    """

    def __init__(self, settings_store: Optional[SystemSettingsStore] = None):
        """
        Initialize ModelUtilityConfigStore

        Args:
            settings_store: SystemSettingsStore instance (will create if not provided)
        """
        self.settings_store = settings_store or SystemSettingsStore()
        self._default_configs = self._get_default_configs()

    def _get_default_configs(self) -> Dict[str, ModelUtilityConfig]:
        """Get default model configurations based on latest model list"""
        return {
            # OpenAI latest models (Nov 2025)
            "gpt-5.1-pro": ModelUtilityConfig(
                model_name="gpt-5.1-pro",
                provider="openai",
                cost_per_1m_tokens=15.0,  # Latest premium model
                success_rate=0.97,
                latency_ms=3000,
            ),
            "gpt-5.1": ModelUtilityConfig(
                model_name="gpt-5.1",
                provider="openai",
                cost_per_1m_tokens=10.0,
                success_rate=0.96,
                latency_ms=2500,
            ),
            "gpt-4o": ModelUtilityConfig(
                model_name="gpt-4o",
                provider="openai",
                cost_per_1m_tokens=5.0,
                success_rate=0.95,
                latency_ms=2000,
            ),
            "gpt-4o-mini": ModelUtilityConfig(
                model_name="gpt-4o-mini",
                provider="openai",
                cost_per_1m_tokens=0.15,
                success_rate=0.85,
                latency_ms=800,
            ),
            "gpt-4-turbo": ModelUtilityConfig(
                model_name="gpt-4-turbo",
                provider="openai",
                cost_per_1m_tokens=10.0,
                success_rate=0.92,
                latency_ms=2500,
            ),
            "gpt-3.5-turbo": ModelUtilityConfig(
                model_name="gpt-3.5-turbo",
                provider="openai",
                cost_per_1m_tokens=0.5,
                success_rate=0.80,
                latency_ms=500,
            ),
            # Anthropic latest models (Oct 2025)
            "claude-opus-4.5": ModelUtilityConfig(
                model_name="claude-opus-4.5",
                provider="anthropic",
                cost_per_1m_tokens=20.0,  # Most powerful
                success_rate=0.98,
                latency_ms=3500,
            ),
            "claude-sonnet-4.5": ModelUtilityConfig(
                model_name="claude-sonnet-4.5",
                provider="anthropic",
                cost_per_1m_tokens=4.0,
                success_rate=0.94,
                latency_ms=2000,
            ),
            "claude-haiku-4.5": ModelUtilityConfig(
                model_name="claude-haiku-4.5",
                provider="anthropic",
                cost_per_1m_tokens=0.3,
                success_rate=0.84,
                latency_ms=700,
            ),
            # Anthropic legacy models
            "claude-3.5-sonnet": ModelUtilityConfig(
                model_name="claude-3.5-sonnet",
                provider="anthropic",
                cost_per_1m_tokens=3.0,
                success_rate=0.93,
                latency_ms=1800,
            ),
            "claude-3-opus": ModelUtilityConfig(
                model_name="claude-3-opus",
                provider="anthropic",
                cost_per_1m_tokens=15.0,
                success_rate=0.96,
                latency_ms=3000,
            ),
            "claude-3-haiku": ModelUtilityConfig(
                model_name="claude-3-haiku",
                provider="anthropic",
                cost_per_1m_tokens=0.25,
                success_rate=0.82,
                latency_ms=600,
            ),
            # Vertex AI Gemini latest models (Nov 2025)
            "gemini-3-pro": ModelUtilityConfig(
                model_name="gemini-3-pro",
                provider="vertex-ai",
                cost_per_1m_tokens=12.0,  # Latest, most capable
                success_rate=0.97,
                latency_ms=2800,
            ),
            "gemini-2.5-pro": ModelUtilityConfig(
                model_name="gemini-2.5-pro",
                provider="vertex-ai",
                cost_per_1m_tokens=8.0,
                success_rate=0.95,
                latency_ms=2200,
            ),
            "gemini-2.5-flash": ModelUtilityConfig(
                model_name="gemini-2.5-flash",
                provider="vertex-ai",
                cost_per_1m_tokens=0.5,
                success_rate=0.88,
                latency_ms=900,
            ),
            "gemini-2.5-flash-lite": ModelUtilityConfig(
                model_name="gemini-2.5-flash-lite",
                provider="vertex-ai",
                cost_per_1m_tokens=0.2,
                success_rate=0.83,
                latency_ms=600,
            ),
            "gemini-1.5-pro": ModelUtilityConfig(
                model_name="gemini-1.5-pro",
                provider="vertex-ai",
                cost_per_1m_tokens=7.0,
                success_rate=0.93,
                latency_ms=2000,
            ),
            "gemini-1.5-flash": ModelUtilityConfig(
                model_name="gemini-1.5-flash",
                provider="vertex-ai",
                cost_per_1m_tokens=0.4,
                success_rate=0.86,
                latency_ms=800,
            ),
            "gemini-pro": ModelUtilityConfig(
                model_name="gemini-pro",
                provider="vertex-ai",
                cost_per_1m_tokens=1.0,
                success_rate=0.85,
                latency_ms=1000,
            ),
        }

    def get_model_config(self, model_name: str) -> Optional[ModelUtilityConfig]:
        """
        Get utility configuration for a model

        Args:
            model_name: Model name

        Returns:
            ModelUtilityConfig or None if not found
        """
        # Try to get from settings
        setting = self.settings_store.get_setting(f"model_utility_config_{model_name}")
        if setting and setting.value:
            try:
                config_data = json.loads(setting.value) if isinstance(setting.value, str) else setting.value
                return ModelUtilityConfig.from_dict(config_data)
            except Exception as e:
                logger.warning(f"Failed to parse model utility config for {model_name}: {e}")

        # Fall back to default
        return self._default_configs.get(model_name)

    def get_all_configs(self) -> Dict[str, ModelUtilityConfig]:
        """
        Get all model utility configurations

        Returns:
            Dictionary mapping model_name to ModelUtilityConfig
        """
        # Get all model utility config settings
        all_settings = self.settings_store.get_settings_by_category("model_utility")
        configs = {}

        for setting in all_settings:
            if setting.key.startswith("model_utility_config_"):
                model_name = setting.key.replace("model_utility_config_", "")
                try:
                    config_data = json.loads(setting.value) if isinstance(setting.value, str) else setting.value
                    configs[model_name] = ModelUtilityConfig.from_dict(config_data)
                except Exception as e:
                    logger.warning(f"Failed to parse model utility config for {model_name}: {e}")

        # Merge with defaults for models not in settings
        for model_name, default_config in self._default_configs.items():
            if model_name not in configs:
                configs[model_name] = default_config

        return configs

    def save_model_config(self, config: ModelUtilityConfig) -> None:
        """
        Save utility configuration for a model

        Args:
            config: ModelUtilityConfig instance
        """
        setting = SystemSetting(
            key=f"model_utility_config_{config.model_name}",
            value=json.dumps(config.to_dict()),
            value_type=SettingType.JSON,
            category="model_utility",
            description=f"Utility configuration for model {config.model_name}",
            metadata={
                "provider": config.provider,
                "model_name": config.model_name,
            }
        )
        self.settings_store.save_setting(setting)
        logger.info(f"Saved utility config for model {config.model_name}")

    def auto_assign_configs_for_enabled_models(self) -> Dict[str, ModelUtilityConfig]:
        """
        Automatically assign utility configurations for enabled models

        This method:
        1. Detects all enabled models from ModelConfigStore
        2. Assigns default configurations for models without configs
        3. Groups models by provider and assigns similar configs

        Returns:
            Dictionary of assigned configurations
        """
        try:
            from backend.app.services.model_config_store import ModelConfigStore

            model_store = ModelConfigStore()
            enabled_models = model_store.get_all_models(enabled=True)

            assigned_configs = {}

            for model in enabled_models:
                model_name = model.model_name
                provider = model.provider_name

                # Check if config already exists
                existing_config = self.get_model_config(model_name)
                if existing_config:
                    assigned_configs[model_name] = existing_config
                    continue

                # Try to find similar model in defaults
                default_config = self._default_configs.get(model_name)
                if default_config:
                    # Use default config
                    assigned_configs[model_name] = default_config
                    self.save_model_config(default_config)
                else:
                    # Infer config from provider and model characteristics
                    inferred_config = self._infer_config_from_model(model_name, provider)
                    assigned_configs[model_name] = inferred_config
                    self.save_model_config(inferred_config)

            logger.info(f"Auto-assigned utility configs for {len(assigned_configs)} enabled models")
            return assigned_configs

        except Exception as e:
            logger.error(f"Failed to auto-assign configs for enabled models: {e}", exc_info=True)
            return {}

    def _infer_config_from_model(self, model_name: str, provider: str) -> ModelUtilityConfig:
        """
        Infer utility configuration from model name and provider

        Uses latest model naming patterns (gpt-5.1, claude-opus-4.5, gemini-3-pro, etc.)

        Args:
            model_name: Model name
            provider: Provider name

        Returns:
            Inferred ModelUtilityConfig
        """
        # Infer based on model name patterns (latest naming conventions)
        model_lower = model_name.lower()

        # OpenAI models
        if provider == "openai":
            if "gpt-5.1-pro" in model_lower or "gpt-5-pro" in model_lower:
                cost = 15.0
                success_rate = 0.97
                latency_ms = 3000
            elif "gpt-5.1" in model_lower or "gpt-5" in model_lower:
                cost = 10.0
                success_rate = 0.96
                latency_ms = 2500
            elif "gpt-4o" in model_lower and "mini" not in model_lower:
                cost = 5.0
                success_rate = 0.95
                latency_ms = 2000
            elif "gpt-4" in model_lower:
                cost = 10.0
                success_rate = 0.92
                latency_ms = 2500
            elif "gpt-3.5" in model_lower or "mini" in model_lower:
                cost = 0.5
                success_rate = 0.80
                latency_ms = 600
            else:
                cost = 1.0
                success_rate = 0.85
                latency_ms = 1000

        # Anthropic models
        elif provider == "anthropic":
            if "opus-4.5" in model_lower or "opus-4" in model_lower:
                cost = 20.0
                success_rate = 0.98
                latency_ms = 3500
            elif "sonnet-4.5" in model_lower or "sonnet-4" in model_lower:
                cost = 4.0
                success_rate = 0.94
                latency_ms = 2000
            elif "haiku-4.5" in model_lower or "haiku-4" in model_lower:
                cost = 0.3
                success_rate = 0.84
                latency_ms = 700
            elif "opus" in model_lower:
                cost = 15.0
                success_rate = 0.96
                latency_ms = 3000
            elif "sonnet" in model_lower:
                cost = 3.0
                success_rate = 0.93
                latency_ms = 1800
            elif "haiku" in model_lower:
                cost = 0.25
                success_rate = 0.82
                latency_ms = 600
            else:
                cost = 2.0
                success_rate = 0.88
                latency_ms = 1500

        # Vertex AI Gemini models
        elif provider == "vertex-ai":
            if "gemini-3-pro" in model_lower:
                cost = 12.0
                success_rate = 0.97
                latency_ms = 2800
            elif "gemini-2.5-pro" in model_lower:
                cost = 8.0
                success_rate = 0.95
                latency_ms = 2200
            elif "gemini-2.5-flash" in model_lower:
                if "lite" in model_lower:
                    cost = 0.2
                    success_rate = 0.83
                    latency_ms = 600
                else:
                    cost = 0.5
                    success_rate = 0.88
                    latency_ms = 900
            elif "gemini-1.5-pro" in model_lower:
                cost = 7.0
                success_rate = 0.93
                latency_ms = 2000
            elif "gemini-1.5-flash" in model_lower:
                cost = 0.4
                success_rate = 0.86
                latency_ms = 800
            elif "gemini" in model_lower and "pro" in model_lower:
                cost = 5.0
                success_rate = 0.90
                latency_ms = 1800
            elif "gemini" in model_lower and "flash" in model_lower:
                cost = 0.3
                success_rate = 0.84
                latency_ms = 700
            elif "gemini" in model_lower:
                cost = 1.0
                success_rate = 0.85
                latency_ms = 1000
            else:
                cost = 1.0
                success_rate = 0.85
                latency_ms = 1000

        else:
            # Default for unknown providers/models
            cost = 1.0
            success_rate = 0.85
            latency_ms = 1000

        return ModelUtilityConfig(
            model_name=model_name,
            provider=provider,
            cost_per_1m_tokens=cost,
            success_rate=success_rate,
            latency_ms=latency_ms,
            enabled=True,
            metadata={
                "inferred": True,
                "inference_method": "pattern_matching",
                "provider": provider
            }
        )

    def get_configs_by_provider(self, provider: str) -> List[ModelUtilityConfig]:
        """
        Get all configurations for a provider

        Args:
            provider: Provider name

        Returns:
            List of ModelUtilityConfig instances
        """
        all_configs = self.get_all_configs()
        return [config for config in all_configs.values() if config.provider == provider]

    def batch_update_configs(self, configs: List[ModelUtilityConfig]) -> None:
        """
        Batch update multiple model configurations

        Args:
            configs: List of ModelUtilityConfig instances
        """
        for config in configs:
            self.save_model_config(config)
        logger.info(f"Batch updated {len(configs)} model utility configs")

