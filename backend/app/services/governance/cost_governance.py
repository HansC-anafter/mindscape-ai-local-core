"""
Cost Governance Service

Implements cost estimation, quota checking, and downgrade recommendations.
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, date

from backend.app.services.governance.stubs import CostGovernanceDecision
from backend.app.services.governance.governance_store import GovernanceStore
from backend.app.services.system_settings_store import SystemSettingsStore
from backend.app.services.model_utility_config_store import ModelUtilityConfigStore
from backend.app.core.runtime_port import ExecutionProfile

logger = logging.getLogger(__name__)


class CostGovernance:
    """Cost governance service for checking cost quotas and providing downgrade recommendations"""

    def __init__(
        self,
        settings_store: Optional[SystemSettingsStore] = None,
        model_config_store: Optional[ModelUtilityConfigStore] = None
    ):
        """
        Initialize CostGovernance

        Args:
            settings_store: SystemSettingsStore instance (will create if not provided)
            model_config_store: ModelUtilityConfigStore instance (will create if not provided)
        """
        self.settings_store = settings_store or SystemSettingsStore()
        self.model_config_store = model_config_store or ModelUtilityConfigStore(
            settings_store=self.settings_store
        )
        self.governance_store = GovernanceStore()

    def _get_quota_settings(self, workspace_id: str) -> Dict[str, Any]:
        """
        Get cost quota settings for workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Dictionary with quota settings
        """
        # Read quota settings from SystemSettingsStore
        default_quota = {
            "daily_quota": self.settings_store.get("governance.cost.quota.daily", 10.0),
            "single_execution_limit": self.settings_store.get("governance.cost.quota.single", 5.0),
            "risk_level_quotas": {
                "read": self.settings_store.get("governance.cost.quota.risk.read", 10.0),
                "write": self.settings_store.get("governance.cost.quota.risk.write", 5.0),
                "publish": self.settings_store.get("governance.cost.quota.risk.publish", 2.0),
            }
        }

        # Try to get workspace-specific quota
        workspace_quota_key = f"governance.cost.quota.{workspace_id}"
        workspace_quota = self.settings_store.get(workspace_quota_key)
        if workspace_quota and isinstance(workspace_quota, dict):
            default_quota.update(workspace_quota)

        return default_quota

    def _estimate_cost(
        self,
        playbook_code: str,
        execution_profile: ExecutionProfile,
        context: Dict[str, Any]
    ) -> float:
        """
        Estimate execution cost based on model pricing and token estimates

        Args:
            playbook_code: Playbook code
            execution_profile: Execution profile
            context: Execution context

        Returns:
            Estimated cost in USD
        """
        # Get token estimates from context
        input_tokens = context.get("estimated_input_tokens", 3000)
        output_tokens = context.get("estimated_output_tokens", 1000)

        # Get model name from context or settings
        model_name = context.get("model_name")
        if not model_name:
            # Try to get from execution profile or settings
            model_name = self.settings_store.get("chat_model", "gpt-5.1")

        # Get model pricing from ModelUtilityConfigStore
        try:
            model_config = self.model_config_store.get_model_config(model_name)
            if not model_config or not model_config.enabled:
                # Fallback to default model
                model_config = self.model_config_store.get_model_config("gpt-5.1")
                if not model_config:
                    logger.warning(f"Model config not found for {model_name}, using default pricing")
                    return 0.0

            # Calculate cost: (input_tokens * input_price + output_tokens * output_price) / 1M
            # For simplicity, assume same price for input and output
            cost_per_1m = model_config.cost_per_1m_tokens
            estimated_cost = (input_tokens + output_tokens) * cost_per_1m / 1_000_000

            # Adjust based on execution mode
            if execution_profile.execution_mode == "durable":
                # Durable mode may require more tokens for checkpointing
                estimated_cost *= 1.2
            elif execution_profile.execution_mode == "simple":
                # Simple mode is more efficient
                estimated_cost *= 0.9

            return estimated_cost

        except Exception as e:
            logger.error(f"Failed to estimate cost: {e}", exc_info=True)
            return 0.0

    def _get_today_usage(self, workspace_id: str) -> float:
        """
        Get today's cost usage for workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Today's cost usage in USD
        """
        try:
            return self.governance_store.get_today_usage(workspace_id)
        except Exception as e:
            logger.warning(f"Failed to query current cost usage: {e}")
            return 0.0

    def _check_quota(
        self,
        estimated_cost: float,
        quota_settings: Dict[str, Any],
        workspace_id: str,
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if estimated cost exceeds quota

        Args:
            estimated_cost: Estimated cost
            quota_settings: Quota settings
            workspace_id: Workspace ID
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        # Check single execution limit
        single_limit = quota_settings.get("single_execution_limit", 5.0)
        if estimated_cost > single_limit:
            return False, f"Estimated cost ${estimated_cost:.2f} exceeds single execution limit ${single_limit:.2f}"

        # Check daily quota
        daily_quota = quota_settings.get("daily_quota", 10.0)
        today_usage = self._get_today_usage(workspace_id)
        if today_usage + estimated_cost > daily_quota:
            return False, f"Estimated cost ${estimated_cost:.2f} would exceed daily quota ${daily_quota:.2f} (current usage: ${today_usage:.2f})"

        # Check risk level quota
        risk_level = context.get("risk_level", "read")
        risk_quota = quota_settings.get("risk_level_quotas", {}).get(risk_level, daily_quota)
        if today_usage + estimated_cost > risk_quota:
            return False, f"Estimated cost ${estimated_cost:.2f} would exceed {risk_level} risk level quota ${risk_quota:.2f}"

        return True, None

    def _get_downgrade_recommendation(
        self,
        playbook_code: str,
        execution_profile: ExecutionProfile,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Get downgrade recommendation when cost exceeds quota

        Args:
            playbook_code: Playbook code
            execution_profile: Execution profile
            context: Execution context

        Returns:
            Downgrade recommendation message
        """
        # Suggest using simpler execution mode
        if execution_profile.execution_mode == "durable":
            return "Consider using 'simple' execution mode to reduce cost"

        # Suggest using cheaper model
        current_model = context.get("model_name", "gpt-5.1")
        cheaper_models = ["gpt-4o-mini", "gpt-3.5-turbo", "claude-haiku-4.5"]
        for model in cheaper_models:
            try:
                model_config = self.model_config_store.get_model_config(model)
                if model_config and model_config.enabled:
                    return f"Consider using {model} model to reduce cost"
            except Exception:
                continue

        return "Consider reducing input/output token usage or using a cheaper model"

    async def check(
        self,
        playbook_code: str,
        execution_profile: ExecutionProfile,
        workspace_id: str,
        context: Dict[str, Any]
    ) -> Optional[CostGovernanceDecision]:
        """
        Check cost governance for playbook execution

        Args:
            playbook_code: Playbook code
            execution_profile: Execution profile
            workspace_id: Workspace ID
            context: Execution context

        Returns:
            CostGovernanceDecision or None if check is disabled
        """
        try:
            # Check if governance is enabled
            governance_enabled = self.settings_store.get("governance.enabled", True)
            if not governance_enabled:
                return None

            # Check if cost governance is enabled
            cost_governance_enabled = self.settings_store.get("governance.cost.enabled", True)
            if not cost_governance_enabled:
                return CostGovernanceDecision(approved=True)

            # Estimate cost
            estimated_cost = self._estimate_cost(playbook_code, execution_profile, context)

            # Get quota settings
            quota_settings = self._get_quota_settings(workspace_id)

            # Check quota
            approved, reason = self._check_quota(estimated_cost, quota_settings, workspace_id, context)

            # Build decision
            decision = CostGovernanceDecision(
                approved=approved,
                reason=reason,
                estimated_cost=estimated_cost
            )

            # Add downgrade recommendation if rejected
            if not approved:
                downgrade_recommendation = self._get_downgrade_recommendation(
                    playbook_code, execution_profile, context
                )
                if downgrade_recommendation:
                    decision.reason = f"{reason}. {downgrade_recommendation}"

            return decision

        except Exception as e:
            logger.error(f"Cost governance check failed: {e}", exc_info=True)
            # On error, approve to avoid blocking execution
            return CostGovernanceDecision(approved=True, reason=f"Cost check error: {str(e)}")
