"""
Node Governance Service

Implements playbook whitelist/blacklist checking, risk label validation, and throttling.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

from backend.app.services.governance.stubs import NodeGovernanceDecision
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


class NodeGovernance:
    """Node governance service for checking playbook whitelist/blacklist and risk labels"""

    def __init__(self, settings_store: Optional[SystemSettingsStore] = None):
        """
        Initialize NodeGovernance

        Args:
            settings_store: SystemSettingsStore instance (will create if not provided)
        """
        self.settings_store = settings_store or SystemSettingsStore()

    def _get_node_settings(self, workspace_id: str) -> Dict[str, Any]:
        """
        Get node governance settings for workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Dictionary with node governance settings
        """
        # Read settings from SystemSettingsStore
        default_settings = {
            "playbook_whitelist": self.settings_store.get("governance.node.playbook_whitelist", []),
            "playbook_blacklist": self.settings_store.get("governance.node.playbook_blacklist", []),
            "risk_labels": self.settings_store.get("governance.node.risk_labels", []),
            "throttle_config": {
                "write_operations_limit": self.settings_store.get("governance.node.throttle.write_limit", 10),
                "queue_strategy": self.settings_store.get("governance.node.throttle.queue_strategy", "reject"),
            }
        }

        # Try to get workspace-specific settings
        workspace_settings_key = f"governance.node.{workspace_id}"
        workspace_settings = self.settings_store.get(workspace_settings_key)
        if workspace_settings and isinstance(workspace_settings, dict):
            default_settings.update(workspace_settings)

        return default_settings

    def _check_whitelist(self, playbook_code: str, whitelist: List[str]) -> bool:
        """
        Check if playbook is in whitelist

        Args:
            playbook_code: Playbook code
            whitelist: List of whitelisted playbook codes

        Returns:
            True if whitelist is empty or playbook is in whitelist
        """
        if not whitelist:
            return True  # No whitelist means all allowed
        return playbook_code in whitelist

    def _check_blacklist(self, playbook_code: str, blacklist: List[str]) -> bool:
        """
        Check if playbook is in blacklist

        Args:
            playbook_code: Playbook code
            blacklist: List of blacklisted playbook codes

        Returns:
            True if playbook is NOT in blacklist
        """
        if not blacklist:
            return True  # No blacklist means all allowed
        return playbook_code not in blacklist

    def _check_risk_labels(
        self,
        playbook_code: str,
        risk_labels: List[str],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if playbook risk labels are allowed

        Args:
            playbook_code: Playbook code
            risk_labels: List of required risk labels
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        # Get playbook risk requirements from context or metadata
        playbook_risk_requirements = context.get("playbook_risk_requirements", [])
        if not playbook_risk_requirements:
            return True, None  # No risk requirements

        # Check if workspace has required risk labels
        workspace_risk_labels = risk_labels or []
        missing_labels = [req for req in playbook_risk_requirements if req not in workspace_risk_labels]

        if missing_labels:
            return False, f"Playbook requires risk labels: {', '.join(missing_labels)}"

        return True, None

    def _check_throttle(
        self,
        playbook_code: str,
        throttle_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check throttling limits

        Args:
            playbook_code: Playbook code
            throttle_config: Throttling configuration
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        # Check if playbook has write operations
        has_write_operations = context.get("has_write_operations", False)
        if not has_write_operations:
            return True, None  # No throttling for read-only operations

        # Get current write operation count
        current_write_count = context.get("current_write_count", 0)
        write_limit = throttle_config.get("write_operations_limit", 10)

        if current_write_count >= write_limit:
            queue_strategy = throttle_config.get("queue_strategy", "reject")
            if queue_strategy == "reject":
                return False, f"Write operations limit ({write_limit}) exceeded"
            elif queue_strategy == "queue":
                return False, f"Write operations limit ({write_limit}) exceeded, please queue"

        return True, None

    async def check(
        self,
        playbook_code: str,
        workspace_id: str,
        context: Dict[str, Any]
    ) -> Optional[NodeGovernanceDecision]:
        """
        Check node governance for playbook execution

        Args:
            playbook_code: Playbook code
            workspace_id: Workspace ID
            context: Execution context

        Returns:
            NodeGovernanceDecision or None if check is disabled
        """
        try:
            # Check if governance is enabled
            governance_enabled = self.settings_store.get("governance.enabled", True)
            if not governance_enabled:
                return None

            # Check governance mode (strict_mode or warning_mode)
            governance_mode = self.settings_store.get("governance.mode", "strict")  # "strict" or "warning"
            is_strict_mode = governance_mode == "strict"

            # Check if node governance is enabled
            node_governance_enabled = self.settings_store.get("governance.node.enabled", True)
            if not node_governance_enabled:
                return NodeGovernanceDecision(approved=True)

            # Get node settings
            node_settings = self._get_node_settings(workspace_id)

            # Check whitelist
            whitelist = node_settings.get("playbook_whitelist", [])
            if not self._check_whitelist(playbook_code, whitelist):
                if is_strict_mode:
                    return NodeGovernanceDecision(
                        approved=False,
                        reason=f"Playbook {playbook_code} is not in whitelist"
                    )
                else:
                    # Warning mode: approve but log warning
                    logger.warning(f"[WARNING MODE] Playbook {playbook_code} is not in whitelist, but allowing execution")
                    return NodeGovernanceDecision(approved=True, reason=f"Warning: Playbook {playbook_code} is not in whitelist (warning mode)")

            # Check blacklist
            blacklist = node_settings.get("playbook_blacklist", [])
            if not self._check_blacklist(playbook_code, blacklist):
                if is_strict_mode:
                    return NodeGovernanceDecision(
                        approved=False,
                        reason=f"Playbook {playbook_code} is in blacklist"
                    )
                else:
                    # Warning mode: approve but log warning
                    logger.warning(f"[WARNING MODE] Playbook {playbook_code} is in blacklist, but allowing execution")
                    return NodeGovernanceDecision(approved=True, reason=f"Warning: Playbook {playbook_code} is in blacklist (warning mode)")

            # Check risk labels
            risk_labels = node_settings.get("risk_labels", [])
            approved, reason = self._check_risk_labels(playbook_code, risk_labels, context)
            if not approved:
                if is_strict_mode:
                    return NodeGovernanceDecision(approved=False, reason=reason)
                else:
                    # Warning mode: approve but log warning
                    logger.warning(f"[WARNING MODE] Risk label check failed: {reason}, but allowing execution")
                    return NodeGovernanceDecision(approved=True, reason=f"Warning: {reason} (warning mode)")

            # Check throttling
            throttle_config = node_settings.get("throttle_config", {})
            approved, reason = self._check_throttle(playbook_code, throttle_config, context)
            if not approved:
                if is_strict_mode:
                    return NodeGovernanceDecision(approved=False, reason=reason)
                else:
                    # Warning mode: approve but log warning
                    logger.warning(f"[WARNING MODE] Throttle check failed: {reason}, but allowing execution")
                    return NodeGovernanceDecision(approved=True, reason=f"Warning: {reason} (warning mode)")

            return NodeGovernanceDecision(approved=True)

        except Exception as e:
            logger.error(f"Node governance check failed: {e}", exc_info=True)
            # On error, approve to avoid blocking execution
            return NodeGovernanceDecision(approved=True, reason=f"Node check error: {str(e)}")

