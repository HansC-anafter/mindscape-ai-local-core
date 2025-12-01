"""
Local Identity Adapter - Single-user, single-workspace mode

Returns ExecutionContext with fixed actor_id and workspace_id for local usage.
"""

from typing import Optional
from ...core.ports.identity_port import IdentityPort
from ...core.execution_context import ExecutionContext


class LocalIdentityAdapter(IdentityPort):
    """
    Local Identity Adapter - Single-user, single-workspace mode
    """

    async def get_current_context(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None
    ) -> ExecutionContext:
        """
        Get local execution context

        Args:
            workspace_id: If provided use this value, otherwise "default"
            profile_id: If provided use this value, otherwise "local-user"

        Returns:
            ExecutionContext with mode="local" tag
        """
        return ExecutionContext(
            actor_id=profile_id or "local-user",
            workspace_id=workspace_id or "default",
            tags={"mode": "local"}
        )

