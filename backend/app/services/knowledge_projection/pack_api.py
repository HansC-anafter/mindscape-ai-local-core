"""Stable capability-pack API for retrievable knowledge projection.

Capability code imports this facade only. Internal storage, authorization,
queue, and graph modules remain Local Core implementation details.
"""

from .retrievable.pack_compiler_support import (
    EmbeddingProvider,
    ObjectResolver,
    compile_owner_object_projection,
)
from .retrievable.task_payload import (
    DescriptorPointer,
    KnowledgeProjectionTaskPayload,
    SourcePointer,
)

__all__ = [
    "DescriptorPointer",
    "EmbeddingProvider",
    "KnowledgeProjectionTaskPayload",
    "ObjectResolver",
    "SourcePointer",
    "compile_owner_object_projection",
]
