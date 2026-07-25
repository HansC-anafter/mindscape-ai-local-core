"""Thin, intentionally unmounted durable workflow route facade."""

from .durable_workflows_core.router import router

__all__ = ("router",)
