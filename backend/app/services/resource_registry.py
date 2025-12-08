"""
Resource Registry

Manages registration and discovery of resource handlers.
Similar to playbook pack registry, but for resource types.
"""

import logging
from typing import Dict, Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .resource_handlers.base import ResourceHandler

logger = logging.getLogger(__name__)


class ResourceRegistry:
    """
    Registry for resource handlers

    Provides registration and discovery of resource handlers,
    similar to playbook pack registry.
    """

    def __init__(self):
        """Initialize the resource registry"""
        self._handlers: Dict[str, Any] = {}

    def register(self, handler: Any) -> None:
        """
        Register a resource handler

        Args:
            handler: ResourceHandler instance
        """
        resource_type = handler.resource_type
        if resource_type in self._handlers:
            logger.warning(f"Resource handler for '{resource_type}' already registered, overwriting")

        self._handlers[resource_type] = handler
        logger.info(f"Registered resource handler: {resource_type}")

    def get(self, resource_type: str) -> Optional[Any]:
        """
        Get a resource handler by type

        Args:
            resource_type: Resource type identifier

        Returns:
            ResourceHandler instance or None if not found
        """
        return self._handlers.get(resource_type)

    def list_types(self) -> list[str]:
        """
        List all registered resource types

        Returns:
            List of resource type identifiers
        """
        return list(self._handlers.keys())

    def is_registered(self, resource_type: str) -> bool:
        """
        Check if a resource type is registered

        Args:
            resource_type: Resource type identifier

        Returns:
            True if registered, False otherwise
        """
        return resource_type in self._handlers


# Global registry instance
_registry: Optional[ResourceRegistry] = None


def get_registry() -> ResourceRegistry:
    """
    Get the global resource registry instance

    Returns:
        ResourceRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ResourceRegistry()
    return _registry


def register_handler(handler: Any) -> None:
    """
    Register a resource handler in the global registry

    Args:
        handler: ResourceHandler instance
    """
    get_registry().register(handler)

