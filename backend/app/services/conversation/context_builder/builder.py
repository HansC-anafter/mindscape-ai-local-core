"""
Context Builder Service

Public facade for building LLM prompt context from workspace data.
"""

from .builder_core import (
    ContextBuilderBase,
    ContextDelegatesMixin,
    ContextSectionsMixin,
    EnhancedPromptMixin,
    PlanningContextMixin,
    QAContextMixin,
)


class ContextBuilder(
    QAContextMixin,
    PlanningContextMixin,
    ContextSectionsMixin,
    ContextDelegatesMixin,
    EnhancedPromptMixin,
    ContextBuilderBase,
):
    """Build context for LLM prompts from workspace data."""
