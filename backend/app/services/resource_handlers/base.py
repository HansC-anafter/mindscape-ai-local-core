"""
Base Resource Handler Interface

Defines the interface for resource handlers in the generic resource routing system.
All resource handlers must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class ResourceHandler(ABC):
    """
    Base interface for resource handlers

    All resource handlers must implement this interface to work with
    the generic resource routing system.
    """

    @property
    @abstractmethod
    def resource_type(self) -> str:
        """Return the resource type identifier (e.g., 'intents', 'chapters')"""
        pass

    @abstractmethod
    async def list(
        self,
        workspace_id: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        List all resources of this type for a workspace

        Args:
            workspace_id: Workspace ID
            filters: Optional filters (e.g., {'status': 'CONFIRMED', 'tree': True})

        Returns:
            List of resource dictionaries
        """
        pass

    @abstractmethod
    async def get(
        self,
        workspace_id: str,
        resource_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single resource by ID

        Args:
            workspace_id: Workspace ID
            resource_id: Resource ID

        Returns:
            Resource dictionary or None if not found
        """
        pass

    @abstractmethod
    async def create(
        self,
        workspace_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new resource

        Args:
            workspace_id: Workspace ID
            data: Resource data dictionary

        Returns:
            Created resource dictionary
        """
        pass

    @abstractmethod
    async def update(
        self,
        workspace_id: str,
        resource_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing resource

        Args:
            workspace_id: Workspace ID
            resource_id: Resource ID
            data: Updated resource data dictionary

        Returns:
            Updated resource dictionary
        """
        pass

    @abstractmethod
    async def delete(
        self,
        workspace_id: str,
        resource_id: str
    ) -> bool:
        """
        Delete a resource

        Args:
            workspace_id: Workspace ID
            resource_id: Resource ID

        Returns:
            True if deleted, False if not found
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the schema for this resource type

        Returns:
            JSON schema dictionary
        """
        return {
            "resource_type": self.resource_type,
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "created_at": {"type": "string"},
                    "updated_at": {"type": "string"}
                },
                "required": ["id"]
            }
        }

