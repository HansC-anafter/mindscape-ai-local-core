"""
Error Handler
Unified error handling and formatting for API errors
"""

import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Error type classification"""
    QUOTA_EXCEEDED = "quota_exceeded"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    SERVER_ERROR = "server_error"
    NETWORK = "network"
    UNKNOWN = "unknown"


class ErrorInfo:
    """Structured error information"""
    def __init__(
        self,
        error_type: ErrorType,
        user_message: str,
        technical_message: Optional[str] = None,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        retryable: bool = False,
        retry_after: Optional[int] = None
    ):
        self.error_type = error_type
        self.user_message = user_message
        self.technical_message = technical_message
        self.error_code = error_code
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "error_type": self.error_type.value,
            "user_message": self.user_message,
            "technical_message": self.technical_message,
            "error_code": self.error_code,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "retry_after": self.retry_after
        }


def parse_api_error(error: Exception) -> ErrorInfo:
    """
    Parse API error and convert to structured ErrorInfo

    Args:
        error: Exception object (can be OpenAI, Anthropic, or other API errors)

    Returns:
        ErrorInfo with user-friendly message and error classification
    """
    error_str = str(error)
    error_lower = error_str.lower()

    # Check for OpenAI API errors
    if hasattr(error, 'response') and hasattr(error.response, 'json'):
        try:
            error_body = error.response.json()
            error_info = error_body.get('error', {})
            error_code = error_info.get('code', '')
            error_message = error_info.get('message', error_str)
            error_type_str = error_info.get('type', '')

            # Handle quota exceeded
            if error_code == 'insufficient_quota' or error_type_str == 'insufficient_quota':
                return ErrorInfo(
                    error_type=ErrorType.QUOTA_EXCEEDED,
                    user_message="API quota exceeded. Please check your plan and billing details.",
                    technical_message=error_message,
                    error_code=error_code,
                    status_code=429,
                    retryable=False
                )

            # Handle rate limit
            if error_code == 'rate_limit_exceeded' or 'rate limit' in error_lower:
                retry_after = None
                if hasattr(error.response, 'headers'):
                    retry_after_header = error.response.headers.get('Retry-After')
                    if retry_after_header:
                        try:
                            retry_after = int(retry_after_header)
                        except ValueError:
                            pass

                return ErrorInfo(
                    error_type=ErrorType.RATE_LIMIT,
                    user_message="Rate limit exceeded. Please try again later.",
                    technical_message=error_message,
                    error_code=error_code,
                    status_code=429,
                    retryable=True,
                    retry_after=retry_after
                )

            # Handle authentication errors
            if error_code in ['invalid_api_key', 'authentication_failed'] or 'authentication' in error_lower:
                return ErrorInfo(
                    error_type=ErrorType.AUTHENTICATION,
                    user_message="Authentication failed. Please check your API key.",
                    technical_message=error_message,
                    error_code=error_code,
                    status_code=401,
                    retryable=False
                )

            # Generic API error
            status_code = getattr(error.response, 'status_code', None)
            return ErrorInfo(
                error_type=ErrorType.SERVER_ERROR,
                user_message=f"API error: {error_message}",
                technical_message=error_str,
                error_code=error_code,
                status_code=status_code,
                retryable=status_code and status_code >= 500
            )
        except Exception:
            pass

    # Check for string-based error messages (fallback)
    if 'quota' in error_lower or 'insufficient_quota' in error_lower:
        return ErrorInfo(
            error_type=ErrorType.QUOTA_EXCEEDED,
            user_message="API quota exceeded. Please check your plan and billing details.",
            technical_message=error_str,
            status_code=429,
            retryable=False
        )

    if 'rate limit' in error_lower or '429' in error_str:
        return ErrorInfo(
            error_type=ErrorType.RATE_LIMIT,
            user_message="Rate limit exceeded. Please try again later.",
            technical_message=error_str,
            status_code=429,
            retryable=True
        )

    if 'not found' in error_lower or '404' in error_str:
        return ErrorInfo(
            error_type=ErrorType.NOT_FOUND,
            user_message="Resource not found.",
            technical_message=error_str,
            status_code=404,
            retryable=False
        )

    # Default: unknown error
    return ErrorInfo(
        error_type=ErrorType.UNKNOWN,
        user_message="An error occurred. Please try again or contact support.",
        technical_message=error_str,
        retryable=False
    )


def format_playbook_error(playbook_code: str, error: Exception) -> Dict[str, Any]:
    """
    Format playbook execution error for API response

    Args:
        playbook_code: Playbook code that failed
        error: Exception that occurred

    Returns:
        Dictionary with structured error information
    """
    error_info = parse_api_error(error)

    return {
        "status": "error",
        "playbook_code": playbook_code,
        "error": error_info.to_dict()
    }

