"""
Agent Dispatch — Bridge control channel mixin.

Handles event-driven workspace assignment via bridge control WebSockets.
"""

import json
import logging
from typing import Any, Dict, Optional

from .models import AgentControlClient

logger = logging.getLogger(__name__)


class BridgeControlMixin:
    """Mixin: bridge control channel for event-driven workspace assignment."""

    async def register_control_client(
        self,
        websocket: Any,
        bridge_id: str,
        owner_user_id: Optional[str] = None,
    ) -> AgentControlClient:
        """Accept and register a bridge control WebSocket."""
        await websocket.accept()
        control = AgentControlClient(
            websocket=websocket,
            bridge_id=bridge_id,
            owner_user_id=owner_user_id,
        )
        self._bridge_controls[bridge_id] = control
        logger.info(
            f"[AgentWS-Control] Bridge {bridge_id} connected "
            f"(owner_user_id={owner_user_id or 'any'})"
        )
        return control

    def unregister_control_client(self, bridge_id: str) -> None:
        """Unregister a bridge control WebSocket."""
        if bridge_id in self._bridge_controls:
            self._bridge_controls.pop(bridge_id, None)
            logger.info(f"[AgentWS-Control] Bridge {bridge_id} disconnected")

    async def _send_control_message(
        self,
        control: AgentControlClient,
        message: Dict[str, Any],
    ) -> bool:
        """Send a control message. Returns False when send fails."""
        try:
            await control.websocket.send_text(json.dumps(message))
            return True
        except Exception as e:
            logger.warning(
                f"[AgentWS-Control] Failed to send to bridge {control.bridge_id}: {e}"
            )
            self.unregister_control_client(control.bridge_id)
            return False

    async def broadcast_workspace_assign(
        self,
        workspace_id: str,
        owner_user_id: Optional[str] = None,
    ) -> int:
        """
        Push assign event to matching bridges.

        If owner_user_id is provided, only bridges with the same owner receive it.
        """
        sent = 0
        for control in list(self._bridge_controls.values()):
            if (
                owner_user_id
                and control.owner_user_id
                and control.owner_user_id != owner_user_id
            ):
                continue
            ok = await self._send_control_message(
                control,
                {
                    "type": "assign",
                    "workspace_id": workspace_id,
                },
            )
            if ok:
                sent += 1
        return sent

    async def broadcast_workspace_unassign(
        self,
        workspace_id: str,
        owner_user_id: Optional[str] = None,
    ) -> int:
        """Push unassign event to matching bridges."""
        sent = 0
        for control in list(self._bridge_controls.values()):
            if (
                owner_user_id
                and control.owner_user_id
                and control.owner_user_id != owner_user_id
            ):
                continue
            ok = await self._send_control_message(
                control,
                {
                    "type": "unassign",
                    "workspace_id": workspace_id,
                },
            )
            if ok:
                sent += 1
        return sent
