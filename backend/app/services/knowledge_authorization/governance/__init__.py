"""Knowledge authorization governance facade."""

from .contracts import (
    KnowledgeAgentMaskInput,
    KnowledgeAccessGrantInput,
    KnowledgeAccessReplacementCommand,
    KnowledgeProjectionActionCommand,
)
from .service import (
    KnowledgeAccessForbiddenError,
    KnowledgeAccessNotFoundError,
    KnowledgeAccessService,
)

__all__ = [
    "KnowledgeAccessForbiddenError",
    "KnowledgeAgentMaskInput",
    "KnowledgeAccessGrantInput",
    "KnowledgeAccessNotFoundError",
    "KnowledgeAccessReplacementCommand",
    "KnowledgeAccessService",
    "KnowledgeProjectionActionCommand",
]
