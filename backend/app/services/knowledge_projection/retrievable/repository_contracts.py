"""Projection repository error contracts."""


class ProjectionWriteConflictError(RuntimeError):
    pass


__all__ = ["ProjectionWriteConflictError"]
