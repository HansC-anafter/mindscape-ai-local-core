from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReceiverSessionPolicy:
    deadline_monotonic: float | None
    reconnect_max_attempts: int

    @classmethod
    def from_args(
        cls,
        args: Any,
        *,
        started_at: float,
        now_epoch: float,
    ) -> "ReceiverSessionPolicy":
        deadlines: list[float] = []
        duration_sec = max(0.0, float(getattr(args, "duration_sec", 0.0) or 0.0))
        if duration_sec > 0:
            deadlines.append(started_at + duration_sec)
        expires_at_epoch = max(
            0.0,
            float(getattr(args, "session_expires_at_epoch", 0.0) or 0.0),
        )
        if expires_at_epoch > 0:
            deadlines.append(started_at + max(0.0, expires_at_epoch - now_epoch))
        return cls(
            deadline_monotonic=min(deadlines) if deadlines else None,
            reconnect_max_attempts=max(
                0,
                int(getattr(args, "stream_reconnect_max_attempts", 0) or 0),
            ),
        )

    def is_complete(self, now_monotonic: float) -> bool:
        return (
            self.deadline_monotonic is not None
            and now_monotonic >= self.deadline_monotonic
        )

    def reconnect_block_reason(
        self,
        *,
        now_monotonic: float,
        outage_attempts: int,
    ) -> str | None:
        if self.is_complete(now_monotonic):
            return "session_deadline_reached"
        if (
            self.reconnect_max_attempts > 0
            and outage_attempts >= self.reconnect_max_attempts
        ):
            return "reconnect_budget_exhausted"
        return None

    def bounded_delay(self, delay_sec: float, *, now_monotonic: float) -> float:
        delay = max(0.0, delay_sec)
        if self.deadline_monotonic is None:
            return delay
        return min(delay, max(0.0, self.deadline_monotonic - now_monotonic))

    def active_elapsed_ms(
        self,
        *,
        started_at: float,
        now_monotonic: float,
    ) -> float | None:
        if self.is_complete(now_monotonic):
            return None
        return max(0.0, (now_monotonic - started_at) * 1000.0)

    def terminal_elapsed_ms(self, *, started_at: float, now_monotonic: float) -> float:
        effective_end = now_monotonic
        if self.deadline_monotonic is not None:
            effective_end = min(effective_end, self.deadline_monotonic)
        return max(0.0, (effective_end - started_at) * 1000.0)


__all__ = ["ReceiverSessionPolicy"]
