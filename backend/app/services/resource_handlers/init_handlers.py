"""
Initialize Resource Handlers

Registers all default resource handlers with the resource registry.
This is called during application startup.
"""

import logging
from .intent_handler import IntentResourceHandler
from .chapter_handler import ChapterResourceHandler
from .artifact_handler import ArtifactResourceHandler
from ..resource_registry import get_registry, register_handler

logger = logging.getLogger(__name__)


def initialize_resource_handlers():
    """
    Initialize and register all default resource handlers

    This function registers system default resource handlers:
    - intents: Intent resource handler
    - chapters: Chapter resource handler
    - artifacts: Artifact resource handler

    Additional handlers can be registered later through the registry.
    """
    registry = get_registry()

    # Register Intent resource handler
    intent_handler = IntentResourceHandler()
    registry.register(intent_handler)
    logger.info("Registered resource handler: intents")

    # Register Chapter resource handler
    chapter_handler = ChapterResourceHandler()
    registry.register(chapter_handler)
    logger.info("Registered resource handler: chapters")

    # Register Artifact resource handler
    artifact_handler = ArtifactResourceHandler()
    registry.register(artifact_handler)
    logger.info("Registered resource handler: artifacts")

    logger.info(f"Initialized {len(registry.list_types())} resource handler(s)")

