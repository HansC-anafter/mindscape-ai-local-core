"""
Playbook Preflight Service

Implements preflight checks for playbook execution: required inputs, credentials, and environment validation.
"""

import logging
from typing import Optional, Dict, Any, List, Tuple

from backend.app.services.governance.stubs import PlaybookPreflightResult, PreflightStatus
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
            "check_required_inputs": self.settings_store.get("governance.preflight.check_required_inputs", True),
            "check_credentials": self.settings_store.get("governance.preflight.check_credentials", True),
            "check_environment": self.settings_store.get("governance.preflight.check_environment", True),
        }

    def _check_required_inputs(
        self,
        playbook_code: str,
        intent_decision: Any,  # IntentRoutingDecision
        context: Dict[str, Any]
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
        required_inputs = intent_decision.required_inputs if hasattr(intent_decision, 'required_inputs') else []
        missing_inputs_from_intent = intent_decision.missing_inputs if hasattr(intent_decision, 'missing_inputs') else []

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
        self,
        playbook_code: str,
        context: Dict[str, Any]
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
        missing_credentials = [cred for cred in required_credentials if cred not in available_credentials]

        if missing_credentials:
            return False, f"Missing required credentials: {', '.join(missing_credentials)}"

        return True, None

    def _check_environment(
        self,
        playbook_code: str,
        context: Dict[str, Any]
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
                return False, "Playbook requires repository access but it is not available"

        # Check API keys if required
        required_api_keys = required_environment.get("required_api_keys", [])
        if required_api_keys:
            available_api_keys = context.get("available_api_keys", [])
            missing_api_keys = [key for key in required_api_keys if key not in available_api_keys]
            if missing_api_keys:
                return False, f"Missing required API keys: {', '.join(missing_api_keys)}"

        return True, None

    def _get_recommended_alternatives(
        self,
        playbook_code: str,
        context: Dict[str, Any]
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
        context: Dict[str, Any]
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
            governance_mode = self.settings_store.get("governance.mode", "strict")  # "strict" or "warning"
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
                credentials_approved, credentials_reason = self._check_credentials(playbook_code, context)

            # Check environment
            environment_approved = True
            environment_reason = None
            if preflight_settings.get("check_environment", True):
                environment_approved, environment_reason = self._check_environment(playbook_code, context)

            # Determine overall status
            if missing_inputs:
                # Missing inputs require clarification
                return PlaybookPreflightResult(
                    playbook_code=playbook_code,
                    status=PreflightStatus.NEED_CLARIFICATION,
                    accepted=False,
                    missing_inputs=missing_inputs,
                    clarification_questions=clarification_questions,
                    recommended_alternatives=self._get_recommended_alternatives(playbook_code, context)
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
                        recommended_alternatives=self._get_recommended_alternatives(playbook_code, context)
                    )
                else:
                    # Warning mode: accept but log warning
                    logger.warning(f"[WARNING MODE] Missing credentials: {credentials_reason}, but allowing execution")
                    return PlaybookPreflightResult(
                        playbook_code=playbook_code,
                        status=PreflightStatus.ACCEPT,
                        accepted=True,
                        rejection_reason=f"Warning: {credentials_reason} (warning mode)"
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
                        recommended_alternatives=self._get_recommended_alternatives(playbook_code, context)
                    )
                else:
                    # Warning mode: accept but log warning
                    logger.warning(f"[WARNING MODE] Environment issues: {environment_reason}, but allowing execution")
                    return PlaybookPreflightResult(
                        playbook_code=playbook_code,
                        status=PreflightStatus.ACCEPT,
                        accepted=True,
                        rejection_reason=f"Warning: {environment_reason} (warning mode)"
                    )

            # All checks passed
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.ACCEPT,
                accepted=True
            )

        except Exception as e:
            logger.error(f"Playbook preflight check failed: {e}", exc_info=True)
            # On error, reject to be safe
            return PlaybookPreflightResult(
                playbook_code=playbook_code,
                status=PreflightStatus.REJECT,
                accepted=False,
                rejection_reason=f"Preflight check error: {str(e)}"
            )

