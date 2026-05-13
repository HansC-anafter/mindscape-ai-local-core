"""Shared PostgreSQL recovery backoff helpers."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_DB_RECOVERY_MARKERS = (
    "database system is in recovery mode",
    "database system is not yet accepting connections",
    "Consistent recovery state has not been yet reached",
)


def _exception_chain_text(exc: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def is_database_recovery_error(exc: BaseException) -> bool:
    message = _exception_chain_text(exc)
    return any(marker in message for marker in _DB_RECOVERY_MARKERS)


@dataclass
class DatabaseRecoveryBackoff:
    delay_seconds: int
    log_interval_seconds: int = 30

    def __post_init__(self) -> None:
        self.delay_seconds = max(1, int(self.delay_seconds or 1))
        self.log_interval_seconds = max(1, int(self.log_interval_seconds or 1))
        self._until_monotonic = 0.0
        self._next_log_monotonic = 0.0

    def note_failure(self, exc: BaseException) -> bool:
        if not is_database_recovery_error(exc):
            return False
        now = time.monotonic()
        self._until_monotonic = max(
            self._until_monotonic,
            now + float(self.delay_seconds),
        )
        return True

    def is_active(self) -> bool:
        return self.remaining_seconds() > 0

    def remaining_seconds(self) -> float:
        return max(0.0, self._until_monotonic - time.monotonic())

    def should_log(self) -> bool:
        now = time.monotonic()
        if now < self._next_log_monotonic:
            return False
        self._next_log_monotonic = now + float(self.log_interval_seconds)
        return True

    def wait_if_active(self, *, label: str) -> None:
        remaining = self.remaining_seconds()
        if remaining <= 0:
            return
        if self.should_log():
            logger.warning(
                "%s paused while PostgreSQL is recovering; remaining_backoff=%.1fs",
                label,
                remaining,
            )
        time.sleep(min(remaining, float(self.delay_seconds)))
