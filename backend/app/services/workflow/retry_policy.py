"""Retry-policy helpers for workflow execution."""

from backend.app.models.playbook import PlaybookKind, RetryPolicy


def default_retry_policy(kind: PlaybookKind) -> RetryPolicy:
    """Get default retry policy based on playbook kind."""
    if kind == PlaybookKind.SYSTEM_TOOL:
        return RetryPolicy(
            max_retries=3,
            retry_delay=1.0,
            exponential_backoff=True,
            retryable_errors=[],
        )
    return RetryPolicy(
        max_retries=1,
        retry_delay=2.0,
        exponential_backoff=False,
        retryable_errors=[],
    )


def calculate_retry_delay(attempt: int, retry_policy: RetryPolicy) -> float:
    """Calculate retry delay based on attempt number and policy."""
    if retry_policy.exponential_backoff:
        return retry_policy.retry_delay * (2 ** (attempt - 1))
    return retry_policy.retry_delay


def classify_error(error: str) -> str:
    """Classify error type for retry decision."""
    error_lower = error.lower()
    if "timeout" in error_lower or "timed out" in error_lower:
        return "timeout"
    if "network" in error_lower or "connection" in error_lower:
        return "network"
    if "rate limit" in error_lower or "quota" in error_lower:
        return "rate_limit"
    if "not found" in error_lower or "missing" in error_lower:
        return "not_found"
    if "permission" in error_lower or "unauthorized" in error_lower:
        return "permission"
    if "validation" in error_lower or "invalid" in error_lower:
        return "validation"
    return "unknown"
