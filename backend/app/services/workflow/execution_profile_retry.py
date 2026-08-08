"""Project a Playbook execution-profile retry contract onto its handoff step."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from backend.app.models.playbook import RetryPolicy


def resolve_handoff_retry_policy(playbook_json: Any) -> Optional[RetryPolicy]:
    """Return the exact declared retry policy for the outer handoff step."""
    profile = getattr(playbook_json, "execution_profile", None)
    if profile is None:
        return None
    if not isinstance(profile, Mapping):
        raise ValueError("playbook_execution_profile_invalid")

    value = profile.get("retry_policy")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("playbook_execution_retry_policy_invalid")

    max_retries = value.get("max_retries", 3)
    retry_delay = value.get("retry_delay", 1.0)
    exponential_backoff = value.get("exponential_backoff", True)
    retryable_errors = value.get("retryable_errors", [])
    if (
        isinstance(max_retries, bool)
        or not isinstance(max_retries, int)
        or max_retries < 0
        or isinstance(retry_delay, bool)
        or not isinstance(retry_delay, (int, float))
        or retry_delay < 0
        or not isinstance(exponential_backoff, bool)
        or not isinstance(retryable_errors, list)
        or any(not isinstance(item, str) for item in retryable_errors)
    ):
        raise ValueError("playbook_execution_retry_policy_invalid")

    return RetryPolicy(
        max_retries=max_retries,
        retry_delay=float(retry_delay),
        exponential_backoff=exponential_backoff,
        retryable_errors=list(retryable_errors),
    )
