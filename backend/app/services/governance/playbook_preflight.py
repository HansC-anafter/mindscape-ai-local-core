"""
Playbook Preflight Service

Implements preflight checks for playbook execution: required inputs, credentials, and environment validation.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

from backend.app.services.governance.stubs import (
    PlaybookPreflightResult,
    PreflightStatus,
)
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


class PlaybookPreflight:
    """Playbook preflight service for checking required inputs, credentials, and environment"""

    def __init__(self, settings_store: Optional[SystemSettingsStore] = None):
        """
        Initialize PlaybookPreflight

        Args:
            settings_store: SystemSettingsStore instance (will create if not provided)
        """
        self.settings_store = settings_store or SystemSettingsStore()

    def _get_preflight_settings(self) -> Dict[str, Any]:
        """
        Get preflight settings

        Returns:
            Dictionary with preflight settings
        """
        return {
            "check_required_inputs": self.settings_store.get(
                "governance.preflight.check_required_inputs", True
            ),
            "check_credentials": self.settings_store.get(
                "governance.preflight.check_credentials", True
            ),
            "check_environment": self.settings_store.get(
                "governance.preflight.check_environment", True
            ),
        }

    def _check_required_inputs(
        self,
        playbook_code: str,
        intent_decision: Any,  # IntentRoutingDecision
        context: Dict[str, Any],
    ) -> Tuple[List[str], List[str]]:
        """
        Check if required inputs are provided

        Args:
            playbook_code: Playbook code
            intent_decision: Intent routing decision
            context: Execution context

        Returns:
            Tuple of (missing_inputs, clarification_questions)
        """
        missing_inputs = []
        clarification_questions = []

        # Get required inputs from intent_decision
        required_inputs = (
            intent_decision.required_inputs
            if hasattr(intent_decision, "required_inputs")
            else []
        )
        missing_inputs_from_intent = (
            intent_decision.missing_inputs
            if hasattr(intent_decision, "missing_inputs")
            else []
        )

        # Get playbook metadata from context
        playbook_metadata = context.get("playbook_metadata", {})
        playbook_required_inputs = playbook_metadata.get("required_inputs", [])

        # Combine all required inputs
        all_required_inputs = list(set(required_inputs + playbook_required_inputs))

        # Get provided inputs from context
        provided_inputs = context.get("provided_inputs", {})

        # Check each required input
        for input_name in all_required_inputs:
            if input_name not in provided_inputs or not provided_inputs[input_name]:
                missing_inputs.append(input_name)
                clarification_questions.append(f"Please provide {input_name}")

        # Also check missing inputs from intent decision
        for input_name in missing_inputs_from_intent:
            if input_name not in missing_inputs:
                missing_inputs.append(input_name)
                clarification_questions.append(f"Please provide {input_name}")

        return missing_inputs, clarification_questions

    def _check_credentials(
        self, playbook_code: str, context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if required credentials are available

        Args:
            playbook_code: Playbook code
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        # Get playbook metadata from context
        playbook_metadata = context.get("playbook_metadata", {})
        required_credentials = playbook_metadata.get("required_credentials", [])

        if not required_credentials:
            return True, None  # No credentials required

        # Get available credentials from context
        available_credentials = context.get("available_credentials", [])

        # Check each required credential
        missing_credentials = [
            cred for cred in required_credentials if cred not in available_credentials
        ]

        if missing_credentials:
            return (
                False,
                f"Missing required credentials: {', '.join(missing_credentials)}",
            )

        return True, None

    def _check_environment(
        self, playbook_code: str, context: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if environment requirements are met

        Args:
            playbook_code: Playbook code
            context: Execution context

        Returns:
            Tuple of (approved, reason)
        """
        # Get playbook metadata from context
        playbook_metadata = context.get("playbook_metadata", {})
        required_environment = playbook_metadata.get("required_environment", {})

        if not required_environment:
            return True, None  # No environment requirements

        # Check sandbox_id if required
        if required_environment.get("requires_sandbox", False):
            sandbox_id = context.get("sandbox_id")
            if not sandbox_id:
                return False, "Playbook requires sandbox_id but it is not provided"

        # Check repository access if required
        if required_environment.get("requires_repo_access", False):
            repo_access = context.get("repo_access", False)
            if not repo_access:
                return (
                    False,
                    "Playbook requires repository access but it is not available",
                )

        # Check API keys if required
        required_api_keys = required_environment.get("required_api_keys", [])
        if required_api_keys:
            available_api_keys = context.get("available_api_keys", [])
            missing_api_keys = [
                key for key in required_api_keys if key not in available_api_keys
            ]
            if missing_api_keys:
                return (
                    False,
                    f"Missing required API keys: {', '.join(missing_api_keys)}",
                )

        return True, None

    def _get_recommended_alternatives(
        self, playbook_code: str, context: Dict[str, Any]
    ) -> List[str]:
        """
        Get recommended alternative playbooks

        Args:
            playbook_code: Playbook code
            context: Execution context

        Returns:
            List of recommended alternative playbook codes
        """
        # Get alternatives from intent_decision or context
        alternatives = context.get("alternative_playbooks", [])
        return alternatives

    async def preflight(
        self,
        playbook_code: str,
        intent_decision: Any,  # IntentRoutingDecision
        context: Dict[str, Any],
    ) -> PlaybookPreflightResult:
        """
        Perform preflight check for playbook execution

        Args:
            playbook_code: Playbook code
            intent_decision: Intent routing decision
            context: Execution context

        Returns:
            PlaybookPreflightResult
        """
        try:
            # Check governance mode (strict_mode or warning_mode)
            governance_mode = self.settings_store.get(
                "governance.mode", "strict"
            )  # "strict" or "warning"
            is_strict_mode = governance_mode == "strict"

            # Get preflight settings
            preflight_settings = self._get_preflight_settings()

            # Check required inputs
            missing_inputs = []
            clarification_questions = []
            if preflight_settings.get("check_required_inputs", True):
                missing_inputs, clarification_questions = self._check_required_inputs(
                    playbook_code, intent_decision, context
                )

            # Check credentials
            credentials_approved = True
            credentials_reason = None
            if preflight_settings.get("check_credentials", True):
                credentials_approved, credentials_reason = self._check_credentials(
                    playbook_code, context
                )

            # Check environment
            environment_approved = True
            environment_reason = None
            if preflight_settings.get("check_environment", True):
                environment_approved, environment_reason = self._check_environment(
                    playbook_code, context
                )

            # Determine overall status
            if missing_inputs:
                # Missing inputs require clarification
                return PlaybookPreflightResult(
                    playbook_code=playbook_code,
                    status=PreflightStatus.NEED_CLARIFICATION,
                    accepted=False,
                    missing_inputs=missing_inputs,
                    clarification_questions=clarification_questions,
                    recommended_alternatives=self._get_recommended_alternatives(
                        playbook_code, context
                    ),
                )

            if not credentials_approved:
                # Missing credentials
                if is_strict_mode:
                    # Strict mode: reject
                    return PlaybookPreflightResult(
                        playbook_code=playbook_code,
                        status=PreflightStatus.REJECT,
                        accepted=False,
                        rejection_reason=credentials_reason,
                        recommended_alternatives=self._get_recommended_alternatives(
                            playbook_code, context
                        ),
                    )
                else:
                    # Warning mode: accept but log warning
                    logger.warning(
                        f"[WARNING MODE] Missing credentials: {credentials_reason}, but allowing execution"
                    )
                    return PlaybookPreflightResult(
                        playbook_code=playbook_code,
                        status=PreflightStatus.ACCEPT,
                        accepted=True,
                        rejection_reason=f"Warning: {credentials_reason} (warning mode)",
                    )

            if not environment_approved:
                # Environment issues
                if is_strict_mode:
                    # Strict mode: reject
                    return PlaybookPreflightResult(
                        playbook_code=playbook_code,
                        status=PreflightStatus.REJECT,
                        accepted=False,
                        rejection_reason=environment_reason,
                        recommended_alternatives=self._get_recommended_alternatives(
                            playbook_code, context
                        ),
                    )
                else:
                    # Warning mode: accept but log warning
                    logger.warning(
                        f"[WARNING MODE] Environment issues: {environment_reason}, but allowing execution"
                    )
                    return PlaybookPreflightResult(
                        playbook_code=playbook_code,
                        status=PreflightStatus.ACCEPT,
                        accepted=True,
                        rejection_reason=f"Warning: {environment_reason} (warning mode)",
                    )

            # All checks passed
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.ACCEPT,
                accepted=True,
            )

        except Exception as e:
            logger.error(f"Playbook preflight check failed: {e}", exc_info=True)
            # On error, reject to be safe
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.REJECT,
                accepted=False,
                rejection_reason=f"Preflight check error: {str(e)}",
            )

    # ==================== External Agent Preflight ====================

    async def check_external_agent_execution(
        self,
        agent_id: str,
        task: str,
        workspace: Any,  # Workspace model
        context: Optional[Dict[str, Any]] = None,
    ) -> PlaybookPreflightResult:
        """
        Perform preflight check for external agent execution.

        Checks:
        1. Agent is installed and available
        2. Workspace sandbox_config allows the operation
        3. Task risk level assessment

        Args:
            agent_id: External agent identifier (e.g., 'moltbot', 'aider')
            task: Task description to execute
            workspace: Workspace model instance
            context: Optional additional context

        Returns:
            PlaybookPreflightResult with approval status
        """
        playbook_code = f"agent:{agent_id}"
        context = context or {}

        try:
            # Check governance mode
            governance_mode = self.settings_store.get("governance.mode", "strict")
            is_strict_mode = governance_mode == "strict"

            # 1. Check agent availability
            agent_available, agent_error = await self._check_agent_availability(
                agent_id
            )
            if not agent_available:
                return PlaybookPreflightResult(
                    playbook_code=playbook_code,
                    status=PreflightStatus.REJECT,
                    accepted=False,
                    rejection_reason=agent_error
                    or f"Agent {agent_id} is not available",
                )

            # 2. Check sandbox configuration
            sandbox_approved, sandbox_issues = self._check_sandbox_config(
                agent_id, task, workspace, context
            )
            if not sandbox_approved and is_strict_mode:
                return PlaybookPreflightResult(
                    playbook_code=playbook_code,
                    status=PreflightStatus.REJECT,
                    accepted=False,
                    rejection_reason=f"Sandbox config issue: {sandbox_issues}",
                )
            elif not sandbox_approved:
                logger.warning(
                    f"[WARNING MODE] Sandbox issue: {sandbox_issues}, allowing execution"
                )

            # 3. Assess task risk
            risk_level, risk_reasons = self._assess_task_risk(task, workspace, context)

            if risk_level == "high":
                # High risk requires user confirmation
                return PlaybookPreflightResult(
                    playbook_code=playbook_code,
                    status=PreflightStatus.NEED_CLARIFICATION,
                    accepted=False,
                    clarification_questions=[
                        f"This task has HIGH risk level. Reason: {'; '.join(risk_reasons)}. Proceed?",
                    ],
                )
            elif risk_level == "critical":
                # Critical risk is rejected
                return PlaybookPreflightResult(
                    playbook_code=playbook_code,
                    status=PreflightStatus.REJECT,
                    accepted=False,
                    rejection_reason=f"Task has CRITICAL risk level: {'; '.join(risk_reasons)}",
                )

            # All checks passed
            logger.info(
                f"External agent preflight passed: agent={agent_id}, risk={risk_level}"
            )
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.ACCEPT,
                accepted=True,
            )

        except Exception as e:
            logger.error(f"External agent preflight failed: {e}", exc_info=True)
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.REJECT,
                accepted=False,
                rejection_reason=f"Preflight error: {str(e)}",
            )

    async def _check_agent_availability(
        self,
        agent_id: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if the external agent is installed and available.

        Args:
            agent_id: External agent identifier

        Returns:
            Tuple of (available, error_message)
        """
        try:
            from backend.app.services.external_agents.core.registry import (
                get_agent_registry,
            )

            registry = get_agent_registry()

            # Check if agent is registered
            if agent_id not in registry.list_agents():
                return False, f"Agent '{agent_id}' is not registered"

            # Get adapter and check availability
            adapter = registry.get_adapter(agent_id)
            if not adapter:
                return False, f"Agent '{agent_id}' adapter not found"

            # Check if agent CLI is available
            is_available = await adapter.is_available()
            if not is_available:
                return (
                    False,
                    f"Agent '{agent_id}' CLI is not available (not installed or not in PATH)",
                )

            return True, None

        except ImportError as e:
            logger.warning(f"Agent registry not available: {e}")
            return False, "External agent system not available"
        except Exception as e:
            logger.error(f"Error checking agent availability: {e}")
            return False, str(e)

    def _check_sandbox_config(
        self,
        agent_id: str,
        task: str,
        workspace: Any,
        context: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if the workspace sandbox configuration allows the operation.

        Args:
            agent_id: External agent identifier
            task: Task description
            workspace: Workspace model
            context: Execution context

        Returns:
            Tuple of (approved, issue_description)
        """
        # Verify the agent matches workspace preference (unified model - all workspaces equal)
        preferred = getattr(workspace, "preferred_agent", None)
        if preferred and preferred != agent_id:
            return (
                False,
                f"Workspace preferred_agent is '{preferred}', not '{agent_id}'",
            )

        # Get sandbox config
        sandbox_config = getattr(workspace, "sandbox_config", None) or {}

        # Check tool acquire policy
        tool_acquire_policy = sandbox_config.get("tool_acquire_policy", "free")
        if tool_acquire_policy == "blocked":
            # Check if task might involve tool acquisition
            tool_keywords = ["install", "npm", "pip", "download", "clone", "fetch"]
            task_lower = task.lower()
            for keyword in tool_keywords:
                if keyword in task_lower:
                    return (
                        False,
                        f"Tool acquisition is blocked (matched keyword: {keyword})",
                    )

        # Check network allowlist if task involves network
        network_keywords = [
            "fetch",
            "download",
            "api",
            "request",
            "http",
            "curl",
            "wget",
        ]
        task_lower = task.lower()
        involves_network = any(kw in task_lower for kw in network_keywords)

        if involves_network:
            network_allowlist = sandbox_config.get("network_allowlist", [])
            if not network_allowlist:
                logger.debug("Task may involve network, but no allowlist configured")
            # Note: detailed URL validation would happen at execution time

        return True, None

    def _assess_task_risk(
        self,
        task: str,
        workspace: Any,
        context: Dict[str, Any],
    ) -> Tuple[str, List[str]]:
        """
        Assess the risk level of a task.

        Args:
            task: Task description
            workspace: Workspace model
            context: Execution context

        Returns:
            Tuple of (risk_level: "low"|"medium"|"high"|"critical", reasons)
        """
        reasons = []
        task_lower = task.lower()

        # Critical risk patterns (always blocked)
        critical_patterns = [
            ("rm -rf /", "Destructive filesystem operation"),
            ("sudo", "Requires elevated privileges"),
            ("chmod 777", "Insecure permission change"),
            (":(){:|:&};:", "Fork bomb detected"),
            ("mkfs", "Disk formatting detected"),
        ]
        for pattern, reason in critical_patterns:
            if pattern in task_lower:
                reasons.append(reason)
                return "critical", reasons

        # High risk patterns (require confirmation)
        high_risk_patterns = [
            ("delete", "Deletion operation"),
            ("remove", "Removal operation"),
            ("drop table", "Database drop"),
            ("truncate", "Data truncation"),
            ("overwrite", "Overwrite operation"),
            ("force push", "Force push to repository"),
            ("--force", "Force flag detected"),
            ("secrets", "Secrets access"),
            ("password", "Password handling"),
            ("credentials", "Credentials handling"),
            ("api_key", "API key handling"),
            ("token", "Token handling"),
            # Chinese patterns
            ("刪除", "刪除操作"),
            ("移除", "移除操作"),
            ("清除", "清除操作"),
            ("密碼", "密碼操作"),
            ("密鑰", "密鑰操作"),
            ("憑證", "憑證操作"),
        ]
        for pattern, reason in high_risk_patterns:
            if pattern in task_lower:
                reasons.append(reason)

        if reasons:
            return "high", reasons

        # Medium risk patterns
        medium_risk_patterns = [
            ("write", "Write operation"),
            ("modify", "Modify operation"),
            ("update", "Update operation"),
            ("change", "Change operation"),
            ("deploy", "Deployment operation"),
            ("publish", "Publishing operation"),
            # Chinese patterns
            ("寫", "寫入操作"),
            ("修改", "修改操作"),
            ("更新", "更新操作"),
            ("建立", "建立操作"),
            ("創建", "創建操作"),
            ("部署", "部署操作"),
            ("發布", "發布操作"),
            ("執行", "執行操作"),
            ("安裝", "安裝操作"),
        ]
        for pattern, reason in medium_risk_patterns:
            if pattern in task_lower:
                reasons.append(reason)

        if reasons:
            return "medium", reasons

        return "low", []
