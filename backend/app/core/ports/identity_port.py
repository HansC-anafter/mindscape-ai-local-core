"""
Identity Port - Get current execution context
"""

from abc import ABC, abstractmethod
from typing import Optional
from ..domain_context import LocalDomainContext


class IdentityPort(ABC):
    """
    Identity Port - Get current execution context
    """

    @abstractmethod
    async def get_current_context(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> LocalDomainContext:
        """
        Get current execution context

        Args:
            workspace_id: Optional, if provided use this value
            profile_id: Optional, if provided use this value (local mode)

        Returns:
            LocalDomainContext object
        """
        pass

