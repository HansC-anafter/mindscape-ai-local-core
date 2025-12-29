"""
Recovery Handler - Handle errors with RecoveryPolicy from Runtime Profile

Phase 2: Implements retry strategies and fallback modes from RecoveryPolicy.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, Callable, Awaitable
from enum import Enum

from backend.app.models.workspace_runtime_profile import RecoveryPolicy

logger = logging.getLogger(__name__)


class FallbackMode(str, Enum):
    """Fallback mode enum"""
    QA_ONLY = "qa_only"
    READONLY = "readonly"
    ASK_USER = "ask_user"


class RetryStrategy(str, Enum):
    """Retry strategy enum"""
    IMMEDIATE = "immediate"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    ASK_USER = "ask_user"


class RecoveryHandler:
    """
    Recovery Handler - Handle errors with RecoveryPolicy

    Supports:
    - Retry strategies (immediate, exponential_backoff, ask_user)
    - Fallback modes (qa_only, readonly, ask_user)
    - Escalation to human
    """

    def __init__(self, recovery_policy: RecoveryPolicy):
        """
        Initialize Recovery Handler

        Args:
            recovery_policy: RecoveryPolicy configuration
        """
        self.recovery_policy = recovery_policy

    async def handle_error(
        self,
        error: Exception,
        operation: str,
        retry_func: Optional[Callable[[], Awaitable[Any]]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Handle error with RecoveryPolicy

        Args:
            error: Exception that occurred
            operation: Operation description
            retry_func: Optional function to retry (if retry_on_failure is True)
            retry_count: Current retry count

        Returns:
            {
                "handled": bool,
                "action": str,  # "retry", "fallback", "escalate", "fail"
                "fallback_mode": Optional[str],
                "retry_after": Optional[float],  # seconds
                "message": str
            }
        """
        # Check if should escalate to human
        error_type = type(error).__name__
        error_str = str(error).lower()

        should_escalate = any(
            escalation_keyword in error_str
            for escalation_keyword in self.recovery_policy.escalate_to_human_on
        )

        if should_escalate:
            logger.warning(
                f"RecoveryPolicy: Escalating to human for operation '{operation}': {error}"
            )
            return {
                "handled": True,
                "action": "escalate",
                "fallback_mode": None,
                "retry_after": None,
                "message": f"Error escalated to human: {error}"
            }

        # Check if should retry
        if self.recovery_policy.retry_on_failure and retry_func and retry_count < 3:
            retry_strategy = RetryStrategy(self.recovery_policy.retry_strategy)

            if retry_strategy == RetryStrategy.IMMEDIATE:
                logger.info(f"RecoveryPolicy: Retrying immediately (attempt {retry_count + 1})")
                return {
                    "handled": True,
                    "action": "retry",
                    "fallback_mode": None,
                    "retry_after": 0.0,
                    "message": f"Retrying immediately (attempt {retry_count + 1})"
                }

            elif retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
                # Exponential backoff: 1s, 2s, 4s, 8s, ...
                retry_after = min(2 ** retry_count, 60)  # Cap at 60 seconds
                logger.info(
                    f"RecoveryPolicy: Retrying with exponential backoff "
                    f"(attempt {retry_count + 1}, wait {retry_after}s)"
                )
                return {
                    "handled": True,
                    "action": "retry",
                    "fallback_mode": None,
                    "retry_after": retry_after,
                    "message": f"Retrying with exponential backoff (wait {retry_after}s)"
                }

            elif retry_strategy == RetryStrategy.ASK_USER:
                logger.info(f"RecoveryPolicy: Asking user before retry")
                return {
                    "handled": True,
                    "action": "ask_user",
                    "fallback_mode": None,
                    "retry_after": None,
                    "message": f"Error occurred: {error}. Should we retry?"
                }

        # Check if should fallback
        if self.recovery_policy.fallback_on_error:
            fallback_mode = FallbackMode(self.recovery_policy.fallback_mode)
            logger.info(
                f"RecoveryPolicy: Applying fallback mode '{fallback_mode.value}' "
                f"for operation '{operation}'"
            )
            return {
                "handled": True,
                "action": "fallback",
                "fallback_mode": fallback_mode.value,
                "retry_after": None,
                "message": f"Fallback to {fallback_mode.value} mode"
            }

        # Default: fail
        logger.error(f"RecoveryPolicy: No recovery action available, failing: {error}")
        return {
            "handled": False,
            "action": "fail",
            "fallback_mode": None,
            "retry_after": None,
            "message": f"Error not recoverable: {error}"
        }

    async def apply_fallback_mode(
        self,
        fallback_mode: str,
        operation: str
    ) -> Dict[str, Any]:
        """
        Apply fallback mode

        Args:
            fallback_mode: Fallback mode (qa_only, readonly, ask_user)
            operation: Operation description

        Returns:
            {
                "mode": str,
                "restrictions": List[str],
                "message": str
            }
        """
        if fallback_mode == FallbackMode.QA_ONLY.value:
            return {
                "mode": "qa_only",
                "restrictions": ["No tool execution", "QA responses only"],
                "message": "Switched to QA-only mode due to error"
            }
        elif fallback_mode == FallbackMode.READONLY.value:
            return {
                "mode": "readonly",
                "restrictions": ["Read-only operations only", "No write operations"],
                "message": "Switched to read-only mode due to error"
            }
        elif fallback_mode == FallbackMode.ASK_USER.value:
            return {
                "mode": "ask_user",
                "restrictions": [],
                "message": "Asking user for guidance due to error"
            }
        else:
            return {
                "mode": "unknown",
                "restrictions": [],
                "message": f"Unknown fallback mode: {fallback_mode}"
            }

