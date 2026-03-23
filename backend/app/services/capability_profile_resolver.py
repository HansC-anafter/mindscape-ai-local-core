"""
Capability Profile Resolver — maps capability profiles to concrete models.

Three-layer separation (v3.1):
    Layer 1 (AgentSpec): role → capability_profile (e.g. "fast", "precise")
    Layer 2 (Resolver):  capability_profile → (model_name, variant)     ← THIS
    Layer 3 (Infra):     actual API call with resolved model

The resolver reads from system settings deployment-scoped model bindings first,
falling back to built-in defaults.  ``model_name`` may be None, meaning
"use the global chat_model setting".
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class CapabilityProfileResolver:
    """Resolve capability_profile → (model_name, variant_name).

    Model Source-of-Truth chain (v3.1 Fix C):
        resolver.resolve(profile)
          → resolved_model
            → _generate_text(capability_profile=...)
              → _generate_text_via_llm(model=resolved_model)
              → _generate_text_via_executor_runtime(model=resolved_model)
                → context_overrides["model"]
                  → agent_cfg["model"]
                    → payload["model"]
                      → bridge: effective_model = payload.get("model") or ...
    """

    # Profile → graph variant mapping (aligned with VariantType definitions)
    PROFILE_VARIANT_MAP: Dict[str, str] = {
        "fast": "fast_path",  # → VariantType.FAST_PATH
        "standard": "balanced",  # → VariantType.BALANCED
        "precise": "balanced",  # balanced variant + stronger model
        "safe_write": "safe_path",  # → VariantType.SAFE_PATH
        "vision": "balanced",  # vision tasks use balanced variant
    }

    # No hardcoded default model map.
    # Unconfigured profiles → model=None → caller uses global chat_model.

    def resolve(
        self,
        capability_profile: str,
        execution_profile: Optional[Dict[str, Any]] = None,
        deployment_scope: str = "local",
    ) -> Tuple[Optional[str], str]:
        """Return (model_name, variant_name) for the given profile.

        model_name may be None (use global chat_model).
        variant_name always has a value (fallback to 'balanced').

        If execution_profile is provided (from playbook spec), its
        modality requirements may override the profile-based model.
        """
        # Check execution_profile modality needs first
        if execution_profile and "vision" in execution_profile.get("modalities", []):
            # Vision modality needed — use vision profile unless
            # capability_profile already specifies a concrete override
            if capability_profile not in ("precise", "fast"):
                capability_profile = "vision"

        # 1. Check system settings for user-defined overrides
        custom_map = self._load_profile_map(deployment_scope=deployment_scope)
        model = custom_map.get(capability_profile) if custom_map else None

        variant = self.PROFILE_VARIANT_MAP.get(capability_profile, "balanced")

        logger.debug(
            "Resolved profile=%s (scope=%s) → model=%s, variant=%s",
            capability_profile,
            deployment_scope,
            model,
            variant,
        )
        return model, variant

    @staticmethod
    def _load_profile_map(deployment_scope: str = "local") -> Optional[Dict[str, str]]:
        """Load profile model mapping from system settings for the given scope.

        Returns None if not configured or on any error.
        """
        try:
            from backend.app.services.system_settings_store import (
                SystemSettingsStore,
            )

            return SystemSettingsStore().get_profile_model_map_for_scope(
                deployment_scope
            )
        except Exception:
            pass
        return None
