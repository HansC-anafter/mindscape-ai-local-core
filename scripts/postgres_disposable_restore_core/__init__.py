"""Fail-closed disposable PostgreSQL restore implementation seams."""

from .policy import RestoreScope, RestoreSource, validate_restore_scope

__all__ = ["RestoreScope", "RestoreSource", "validate_restore_scope"]
