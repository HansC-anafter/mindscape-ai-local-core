"""
Local Identity Adapter - Single-user, single-workspace mode

Returns LocalDomainContext with fixed actor_id and workspace_id for local usage.
"""

from typing import Optional
from ...core.ports.identity_port import IdentityPort
from ...core.domain_context import LocalDomainContext


class LocalIdentityAdapter(IdentityPort):
    """
    Local Identity Adapter - Single-user, single-workspace mode
    """

    async def get_current_context(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> LocalDomainContext:
        """
        Get local execution context

        Args:
            workspace_id: If provided use this value, otherwise "default"
            profile_id: If provided use this value, otherwise "local-user"

        Returns:
            LocalDomainContext with mode="local" tag
        """
        return LocalDomainContext(
            actor_id=profile_id or "local-user",
            workspace_id=workspace_id or "default",
            tags={"mode": "local"}
        )

