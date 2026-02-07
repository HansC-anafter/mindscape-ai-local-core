"""
Device Node WebSocket Router

Handles WebSocket connections from Device Node for:
- User confirmation requests for sensitive operations
- Audit event reception
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class PendingConfirmation(BaseModel):
    """Pending confirmation request from Device Node"""

    nonce: str
    tool_call_id: str
    tool: str
    arguments: dict
    arguments_hash: str
    trust_level: str
    preview: Optional[str] = None
    expires_at: int
    created_at: datetime = datetime.now()


class DeviceNodeConnectionManager:
    """Manages WebSocket connections from Device Node"""

    def __init__(self):
        self.active_connection: Optional[WebSocket] = None
        self.pending_confirmations: Dict[str, PendingConfirmation] = {}
        self.confirmation_responses: Dict[str, asyncio.Event] = {}
        self.confirmation_results: Dict[str, bool] = {}

    async def connect(self, websocket: WebSocket):
        """Accept Device Node connection"""
        await websocket.accept()
        if self.active_connection:
            logger.warning("Replacing existing Device Node connection")
        self.active_connection = websocket
        logger.info("Device Node connected")

    def disconnect(self):
        """Handle Device Node disconnection"""
        self.active_connection = None
        logger.info("Device Node disconnected")

    async def handle_message(self, message: dict):
        """Process message from Device Node"""
        msg_type = message.get("type")

        if msg_type == "confirmation_request":
            await self._handle_confirmation_request(message.get("payload", {}))
        elif msg_type == "audit_event":
            await self._handle_audit_event(message.get("payload", {}))
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_confirmation_request(self, payload: dict):
        """Store confirmation request for Web Console UI"""
        try:
            confirmation = PendingConfirmation(
                nonce=payload["nonce"],
                tool_call_id=payload["tool_call_id"],
                tool=payload["tool"],
                arguments=payload["arguments"],
                arguments_hash=payload["arguments_hash"],
                trust_level=payload["trust_level"],
                preview=payload.get("preview"),
                expires_at=payload["expires_at"],
            )

            self.pending_confirmations[confirmation.nonce] = confirmation
            self.confirmation_responses[confirmation.nonce] = asyncio.Event()

            logger.info(
                f"Received confirmation request: {confirmation.tool} (nonce: {confirmation.nonce[:8]}...)"
            )

        except KeyError as e:
            logger.error(f"Invalid confirmation request: missing {e}")

    async def _handle_audit_event(self, payload: dict):
        """Log audit event (could also persist to DB)"""
        logger.info(
            f"Audit: {payload.get('tool')} -> {payload.get('result')} "
            f"(trust: {payload.get('trust_level')})"
        )

    def get_pending_confirmations(self) -> list:
        """Get all pending confirmations for Web Console"""
        now = datetime.now().timestamp() * 1000
        active = []
        expired = []

        for nonce, conf in self.pending_confirmations.items():
            if conf.expires_at < now:
                expired.append(nonce)
            else:
                active.append(
                    {
                        "nonce": conf.nonce,
                        "tool_call_id": conf.tool_call_id,
                        "tool": conf.tool,
                        "arguments": conf.arguments,
                        "arguments_hash": conf.arguments_hash,
                        "trust_level": conf.trust_level,
                        "preview": conf.preview,
                        "expires_at": conf.expires_at,
                    }
                )

        for nonce in expired:
            del self.pending_confirmations[nonce]
            if nonce in self.confirmation_responses:
                self.confirmation_responses[nonce].set()
                del self.confirmation_responses[nonce]

        return active

    async def respond_to_confirmation(
        self, nonce: str, tool_call_id: str, arguments_hash: str, approved: bool
    ) -> bool:
        """Send confirmation response to Device Node"""
        if nonce not in self.pending_confirmations:
            logger.warning(f"Unknown confirmation nonce: {nonce}")
            return False

        conf = self.pending_confirmations[nonce]

        if conf.tool_call_id != tool_call_id:
            logger.error(f"Tool call ID mismatch for nonce {nonce}")
            return False

        if conf.arguments_hash != arguments_hash:
            logger.error(f"Arguments hash mismatch for nonce {nonce}")
            return False

        if not self.active_connection:
            logger.error("No active Device Node connection")
            return False

        response = {
            "type": "confirmation_response",
            "payload": {
                "nonce": nonce,
                "tool_call_id": tool_call_id,
                "arguments_hash": arguments_hash,
                "approved": approved,
            },
        }

        await self.active_connection.send_json(response)

        del self.pending_confirmations[nonce]
        if nonce in self.confirmation_responses:
            self.confirmation_results[nonce] = approved
            self.confirmation_responses[nonce].set()

        logger.info(
            f"Sent confirmation response: {nonce[:8]}... -> {'approved' if approved else 'denied'}"
        )
        return True


# Global connection manager
device_node_manager = DeviceNodeConnectionManager()


@router.websocket("/ws/device-node")
async def device_node_websocket(websocket: WebSocket):
    """WebSocket endpoint for Device Node connections"""
    await device_node_manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await device_node_manager.handle_message(message)
            except json.JSONDecodeError:
                logger.error("Invalid JSON from Device Node")
    except WebSocketDisconnect:
        device_node_manager.disconnect()


@router.get("/device-node/confirmations")
async def get_pending_confirmations():
    """Get pending confirmation requests for Web Console"""
    return {
        "confirmations": device_node_manager.get_pending_confirmations(),
        "connected": device_node_manager.active_connection is not None,
    }


@router.post("/device-node/confirmations/{nonce}/respond")
async def respond_to_confirmation(nonce: str, response: dict):
    """Respond to a confirmation request"""
    success = await device_node_manager.respond_to_confirmation(
        nonce=nonce,
        tool_call_id=response.get("tool_call_id", ""),
        arguments_hash=response.get("arguments_hash", ""),
        approved=response.get("approved", False),
    )

    return {"success": success}
