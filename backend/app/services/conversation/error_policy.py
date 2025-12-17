"""
Error Policy

Centralized error handling and logging policy for execution coordination.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PlaybookNotFoundError(Exception):
    """Raised when playbook cannot be found"""

    pass


class ProjectNotFoundError(Exception):
    """Raised when project cannot be found"""

    pass


class MissingExecutionIdWarning(Warning):
    """Warning when execution_id is missing from execution result"""

    pass


class ErrorPolicy:
    """
    Centralized error handling policy

    Responsibilities:
    - Define expected error types
    - Provide error handling helpers
    - Centralize logging levels
    """

    @staticmethod
    def log_and_raise(
        error: Exception,
        message: str,
        log_level: int = logging.ERROR,
    ) -> None:
        """
        Log error and raise exception

        Args:
            error: Exception to raise
            message: Log message
            log_level: Logging level (default: ERROR)
        """
        logger.log(log_level, message, exc_info=True)
        raise error

    @staticmethod
    def warn_and_continue(
        message: str,
        exception: Optional[Exception] = None,
    ) -> None:
        """
        Log warning and continue execution

        Args:
            message: Warning message
            exception: Optional exception for context
        """
        if exception:
            logger.warning(f"{message}: {exception}", exc_info=True)
        else:
            logger.warning(message)

    @staticmethod
    def handle_execution_error(
        operation: str,
        error: Exception,
        raise_on_error: bool = False,
    ) -> None:
        """
        Handle execution error with appropriate policy

        Args:
            operation: Operation description
            error: Exception that occurred
            raise_on_error: Whether to raise exception (default: False)
        """
        message = f"Failed to {operation}: {error}"

        if raise_on_error:
            ErrorPolicy.log_and_raise(error, message)
        else:
            ErrorPolicy.warn_and_continue(message, error)

    @staticmethod
    def handle_missing_execution_id(
        playbook_code: str,
        execution_result: Optional[dict],
    ) -> None:
        """
        Handle missing execution_id warning

        Args:
            playbook_code: Playbook code
            execution_result: Execution result dict
        """
        message = (
            f"Playbook {playbook_code} started but no execution_id returned. "
            f"Result: {execution_result}"
        )
        logger.warning(message)
