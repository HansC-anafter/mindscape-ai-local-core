"""
Resource Handlers

Resource handlers for the generic resource routing system.
Each handler implements the ResourceHandler interface for a specific resource type.
"""

from .base import ResourceHandler
from .intent_handler import IntentResourceHandler
from .chapter_handler import ChapterResourceHandler
from .artifact_handler import ArtifactResourceHandler

__all__ = [
    'ResourceHandler',
    'IntentResourceHandler',
    'ChapterResourceHandler',
    'ArtifactResourceHandler'
]
