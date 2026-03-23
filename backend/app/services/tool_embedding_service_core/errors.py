"""Errors raised by ToolEmbeddingService helpers."""


class MultiModelIndexingError(RuntimeError):
    """Raised when every stale model fails to index successfully."""
