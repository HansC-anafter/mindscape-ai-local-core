"""
Stage Profile Mapper

Maps execution stages to capability profiles for staged model switching.

Stages:
- intent_analysis: ToolCandidateSelection (fast recall)
- scope_decision: Scope resolution
- plan_generation: Plan/ChangeSet generation
- tool_call_generation: Tool-call JSON generation
- tool_call_repair: Format/structure repair loop (TODO: implement repair stage)
- response_formatting: Result formatting/reply
"""

import logging
from typing import Optional
from backend.app.services.conversation.capability_profile import CapabilityProfile, CapabilityProfileRegistry
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


class StageProfileMapper:
    """Maps execution stages to capability profiles"""

    # Default stage to profile mapping
    STAGE_PROFILE_MAP = {
        "intent_analysis": CapabilityProfile.FAST,
        "scope_decision": CapabilityProfile.SAFE_WRITE,
        "plan_generation": CapabilityProfile.PRECISE,
        "tool_call_generation": CapabilityProfile.TOOL_STRICT,
        "tool_call_repair": CapabilityProfile.TOOL_STRICT,  # Format/structure repair loop (TODO: implement repair stage)
        "response_formatting": CapabilityProfile.STANDARD,
    }

    def __init__(self, registry: Optional[CapabilityProfileRegistry] = None):
        """
        Initialize Stage Profile Mapper

        Args:
            registry: CapabilityProfileRegistry instance (optional, will create if not provided)
        """
        self.registry = registry or CapabilityProfileRegistry()

    def get_profile_for_stage(
        self,
        stage: str,
        risk_level: str = "read",
        user_profile_override: Optional[CapabilityProfile] = None
    ) -> CapabilityProfile:
        """
        Get capability profile for execution stage

        Priority:
        1. User override (highest priority)
        2. SystemSettings capability_profile_mapping (if exists)
        3. Risk level adjustment
        4. Default mapping

        Args:
            stage: Stage name (e.g., "intent_analysis", "plan_generation")
            risk_level: Risk level ("read", "write", "publish")
            user_profile_override: User-specified profile override (highest priority)

        Returns:
            CapabilityProfile instance
        """
        # 1. User override (highest priority)
        if user_profile_override:
            return user_profile_override

        # 2. Read from SystemSettings capability_profile_mapping (if exists)
        try:
            settings_store = SystemSettingsStore()
            stage_mapping = settings_store.get_capability_profile_mapping()
            if stage_mapping and stage in stage_mapping:
                profile_name = stage_mapping[stage]
                try:
                    profile = CapabilityProfile(profile_name)
                    logger.debug(f"Using SystemSettings mapping for stage {stage}: {profile_name}")
                    return profile
                except ValueError:
                    logger.warning(f"Invalid profile name '{profile_name}' in SystemSettings for stage {stage}, using default")
        except Exception as e:
            logger.debug(f"Failed to read capability_profile_mapping from SystemSettings: {e}")

        # 3. Adjust based on risk level (write/publish need more conservative profiles)
        if risk_level in ["write", "publish"]:
            if stage == "scope_decision":
                return CapabilityProfile.SAFE_WRITE
            elif stage == "plan_generation":
                return CapabilityProfile.PRECISE

        # 4. Default mapping
        return self.STAGE_PROFILE_MAP.get(
            stage,
            CapabilityProfile.STANDARD
        )

