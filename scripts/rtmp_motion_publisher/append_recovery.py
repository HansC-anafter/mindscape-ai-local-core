from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppendConfirmationSchedule:
    confirmation_round: int
    first_failure_monotonic: float
    next_attempt_monotonic: float
    retry_delay_sec: float


def schedule_append_confirmation(
    *,
    now_monotonic: float,
    first_failure_monotonic: float | None,
    completed_rounds: int,
    maximum_rounds: int,
    base_backoff_sec: float,
    maximum_recovery_sec: float,
) -> AppendConfirmationSchedule | None:
    """Return the next bounded retry without changing window identity."""

    first_failure = (
        now_monotonic
        if first_failure_monotonic is None
        else first_failure_monotonic
    )
    elapsed = max(0.0, now_monotonic - first_failure)
    if completed_rounds >= max(0, maximum_rounds):
        return None
    if elapsed >= max(0.0, maximum_recovery_sec):
        return None
    confirmation_round = completed_rounds + 1
    requested_delay = max(0.0, base_backoff_sec) * (
        2 ** max(0, confirmation_round - 1)
    )
    retry_delay = min(
        requested_delay,
        max(0.0, maximum_recovery_sec - elapsed),
    )
    return AppendConfirmationSchedule(
        confirmation_round=confirmation_round,
        first_failure_monotonic=first_failure,
        next_attempt_monotonic=now_monotonic + retry_delay,
        retry_delay_sec=retry_delay,
    )


__all__ = ["AppendConfirmationSchedule", "schedule_append_confirmation"]
