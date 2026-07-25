"""Shared durable workflow facade errors."""


class DurableWorkflowConflict(RuntimeError):
    """Raised on stale sequence, divergent idempotency, or rollover misuse."""
