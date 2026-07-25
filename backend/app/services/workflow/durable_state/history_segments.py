"""History segment policy shared by facade and compatibility tests."""

MAX_EVENTS = 10_000
MAX_CANONICAL_BYTES = 64 * 1024 * 1024


def rollover_due(event_count: int, canonical_bytes: int) -> bool:
    return event_count >= MAX_EVENTS or canonical_bytes >= MAX_CANONICAL_BYTES
