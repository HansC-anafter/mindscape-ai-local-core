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
    required_capabilities: List[str]  # Required capabilities
    max_latency_ms: int
    max_cost_per_1k_tokens: float


class CapabilityProfileRegistry:
    """Capability profile registry backed by model-routing-registry."""

    def __init__(self):
        self.profiles: Dict[CapabilityProfile, ProfileConfig] = {
            CapabilityProfile.FAST: ProfileConfig(
                profile=CapabilityProfile.FAST,
                required_capabilities=["json_strict"],
                max_latency_ms=1000,
                max_cost_per_1k_tokens=0.002,
            ),
            CapabilityProfile.STANDARD: ProfileConfig(
                profile=CapabilityProfile.STANDARD,
                required_capabilities=["json_strict", "tool_calling"],
                max_latency_ms=3000,
                max_cost_per_1k_tokens=0.01,
            ),
            CapabilityProfile.PRECISE: ProfileConfig(
                profile=CapabilityProfile.PRECISE,
                required_capabilities=["strong_reasoning", "json_strict"],
                max_latency_ms=8000,
                max_cost_per_1k_tokens=0.03,
            ),
            CapabilityProfile.TOOL_STRICT: ProfileConfig(
                profile=CapabilityProfile.TOOL_STRICT,
                required_capabilities=["json_strict", "tool_calling", "schema_validation"],
                max_latency_ms=5000,
                max_cost_per_1k_tokens=0.03,
            ),
            CapabilityProfile.SAFE_WRITE: ProfileConfig(
                profile=CapabilityProfile.SAFE_WRITE,
                required_capabilities=["strong_reasoning", "conservative_scope"],
                max_latency_ms=8000,
                max_cost_per_1k_tokens=0.03,
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
            Model name, or None when the profile has no registry binding.
        """
        from backend.app.services.model_routing_policy_service import (
            ModelRoutingPolicyService,
        )

        try:
            route = ModelRoutingPolicyService().resolve_profile_model(
                profile=profile.value,
                scope="local",
            )
        except ValueError as exc:
            logger.warning(
                "Capability profile %s registry binding is invalid: %s",
                profile.value,
                exc,
            )
            return None

        if not route.model_name:
            return None
        return route.model_name
