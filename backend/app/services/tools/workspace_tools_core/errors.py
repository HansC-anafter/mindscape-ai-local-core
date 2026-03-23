"""Errors raised by workspace tool helpers."""


class WorkspaceQueryValidationError(ValueError):
    """Raised when a workspace SQL query violates the read-only contract."""
