"""
Policy Service

Implements role-based access control, data domain policies, and PII handling checks.
"""

import logging
from typing import Optional, Dict, Any, Tuple

from backend.app.services.governance.stubs import PolicyDecision
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


class PolicyService:
    """Policy service for checking role permissions, data domain policies, and PII handling"""

    def __init__(self, settings_store: Optional[SystemSettingsStore] = None):
        """
        Initialize PolicyService

        Args:
            settings_store: SystemSettingsStore instance (will create if not provided)
        """
        self.settings_store = settings_store or SystemSettingsStore()

    def _get_policy_settings(self, workspace_id: str) -> Dict[str, Any]:
        """
        Get policy settings for workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Dictionary with policy settings
        """
        # Read settings from SystemSettingsStore
        default_settings = {
            "role_policies": self.settings_store.get("governance.policy.role_policies", {}),
            "data_domain_policies": self.settings_store.get("governance.policy.data_domain_policies", {}),
            "pii_handling": self.settings_store.get("governance.policy.pii_handling", {
                "enabled": True,
                "allowed_domains": []
            }),
            "cross_project_access": self.settings_store.get("governance.policy.cross_project_access", {
                "enabled": False,
                "allowed_projects": []
            })
        }

        # Try to get workspace-specific settings
        workspace_settings_key = f"governance.policy.{workspace_id}"
        workspace_settings = self.settings_store.get(workspace_settings_key)
        if workspace_settings and isinstance(workspace_settings, dict):
            default_settings.update(workspace_settings)

        return default_settings

    def _check_role_permissions(
        self,
        playbook_code: str,
        user_id: Optional[str],
        role_policies: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check role-based permissions

        Args:
            playbook_code: Playbook code
            user_id: User ID
            role_policies: Role policies configuration
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        if not role_policies:
            return True, None  # No role policies means all allowed

        # Get user role from context
        user_role = context.get("user_role")
        if not user_role:
            # If no role specified, check if anonymous access is allowed
            if not role_policies.get("allow_anonymous", False):
                return False, "Role-based access control requires user authentication"

        # Get playbook required role
        playbook_required_role = context.get("playbook_required_role")
        if playbook_required_role:
            # Check if user role matches required role
            allowed_roles = role_policies.get("allowed_roles", [])
            if playbook_required_role not in allowed_roles:
                return False, f"Playbook requires role {playbook_required_role}, but user has {user_role}"

        # Check role-specific playbook restrictions
        role_restrictions = role_policies.get("role_restrictions", {})
        if user_role in role_restrictions:
            restricted_playbooks = role_restrictions[user_role].get("restricted_playbooks", [])
            if playbook_code in restricted_playbooks:
                return False, f"Playbook {playbook_code} is restricted for role {user_role}"

        return True, None

    def _check_data_domain_policies(
        self,
        playbook_code: str,
        data_domain_policies: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check data domain policies

        Args:
            playbook_code: Playbook code
            data_domain_policies: Data domain policies configuration
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        if not data_domain_policies:
            return True, None  # No data domain policies means all allowed

        # Get playbook data domains from context
        playbook_data_domains = context.get("playbook_data_domains", [])
        if not playbook_data_domains:
            return True, None  # No data domains specified

        # Check if data domains are allowed
        allowed_domains = data_domain_policies.get("allowed_domains", [])
        restricted_domains = data_domain_policies.get("restricted_domains", [])

        for domain in playbook_data_domains:
            if domain in restricted_domains:
                return False, f"Data domain {domain} is restricted"
            if allowed_domains and domain not in allowed_domains:
                return False, f"Data domain {domain} is not in allowed domains"

        return True, None

    def _check_pii_handling(
        self,
        playbook_code: str,
        pii_handling: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check PII handling policies

        Args:
            playbook_code: Playbook code
            pii_handling: PII handling configuration
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        if not pii_handling.get("enabled", True):
            return True, None  # PII handling check disabled

        # Check if playbook handles PII
        playbook_handles_pii = context.get("playbook_handles_pii", False)
        if not playbook_handles_pii:
            return True, None  # No PII handling required

        # Check if PII handling is allowed for this playbook
        allowed_domains = pii_handling.get("allowed_domains", [])
        playbook_domain = context.get("playbook_data_domain")
        if playbook_domain and playbook_domain not in allowed_domains:
            return False, f"PII handling not allowed for data domain {playbook_domain}"

        return True, None

    def _check_cross_project_access(
        self,
        playbook_code: str,
        workspace_id: str,
        project_id: Optional[str],
        cross_project_access: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check cross-project access policies (Cloud-only)

        Args:
            playbook_code: Playbook code
            workspace_id: Workspace ID
            project_id: Project ID
            cross_project_access: Cross-project access configuration
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        if not cross_project_access.get("enabled", False):
            # Cross-project access disabled, check if playbook is accessing different project
            playbook_project_id = context.get("playbook_project_id")
            if playbook_project_id and playbook_project_id != project_id:
                return False, "Cross-project access is not allowed"

        # Check if project is in allowed projects list
        allowed_projects = cross_project_access.get("allowed_projects", [])
        if allowed_projects and project_id and project_id not in allowed_projects:
            return False, f"Project {project_id} is not in allowed projects list"

        return True, None

    async def check(
        self,
        playbook_code: str,
        workspace_id: str,
        user_id: Optional[str],
        context: Dict[str, Any]
    ) -> Optional[PolicyDecision]:
        """
        Check policy for playbook execution

        Args:
            playbook_code: Playbook code
            workspace_id: Workspace ID
            user_id: User ID
            context: Execution context

        Returns:
            PolicyDecision or None if check is disabled
        """
        try:
            # Check if governance is enabled
            governance_enabled = self.settings_store.get("governance.enabled", True)
            if not governance_enabled:
                return None

            # Check if policy service is enabled
            policy_service_enabled = self.settings_store.get("governance.policy.enabled", True)
            if not policy_service_enabled:
                return PolicyDecision(approved=True)

            # Get policy settings
            policy_settings = self._get_policy_settings(workspace_id)

            # Check role permissions
            role_policies = policy_settings.get("role_policies", {})
            approved, reason = self._check_role_permissions(playbook_code, user_id, role_policies, context)
            if not approved:
                return PolicyDecision(approved=False, reason=reason)

            # Check data domain policies
            data_domain_policies = policy_settings.get("data_domain_policies", {})
            approved, reason = self._check_data_domain_policies(playbook_code, data_domain_policies, context)
            if not approved:
                return PolicyDecision(approved=False, reason=reason)

            # Check PII handling
            pii_handling = policy_settings.get("pii_handling", {})
            approved, reason = self._check_pii_handling(playbook_code, pii_handling, context)
            if not approved:
                return PolicyDecision(approved=False, reason=reason)

            # Check cross-project access (Cloud-only)
            cross_project_access = policy_settings.get("cross_project_access", {})
            project_id = context.get("project_id")
            approved, reason = self._check_cross_project_access(
                playbook_code, workspace_id, project_id, cross_project_access, context
            )
            if not approved:
                return PolicyDecision(approved=False, reason=reason)

            return PolicyDecision(approved=True)

        except Exception as e:
            logger.error(f"Policy service check failed: {e}", exc_info=True)
            # On error, approve to avoid blocking execution
            return PolicyDecision(approved=True, reason=f"Policy check error: {str(e)}")

