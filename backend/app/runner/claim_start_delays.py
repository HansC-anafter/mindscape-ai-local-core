"""Deterministic post-claim start delays for bursty browser workloads."""

from __future__ import annotations

from dataclasses import dataclass


MAX_CLAIM_START_DELAY_MS = 120_000


def parse_claim_start_delays_ms(raw: str | None) -> tuple[int, ...]:
    """Parse a comma-separated delay cycle, defaulting to immediate start."""

    if raw is None or not raw.strip():
        return (0,)

    delays: list[int] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            delay_ms = int(value)
        except ValueError as exc:
            raise ValueError("invalid_runner_post_claim_start_delay_ms") from exc
        if delay_ms < 0 or delay_ms > MAX_CLAIM_START_DELAY_MS:
            raise ValueError("runner_post_claim_start_delay_ms_out_of_range")
        delays.append(delay_ms)

    return tuple(delays) or (0,)


@dataclass
class ClaimStartDelayCycle:
    """Assign delays only to successfully claimed tasks."""

    delays_ms: tuple[int, ...]
    cursor: int = 0

    @classmethod
    def from_raw(cls, raw: str | None) -> "ClaimStartDelayCycle":
        return cls(parse_claim_start_delays_ms(raw))

    def peek_ms(self) -> int:
        return self.delays_ms[self.cursor % len(self.delays_ms)]

    def commit(self) -> None:
        self.cursor += 1

