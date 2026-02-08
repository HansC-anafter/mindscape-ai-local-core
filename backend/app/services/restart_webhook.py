"""
Restart Webhook Service

Sends restart commands to Device Node for infrastructure management.
Only triggers after validation passes.
"""

import os
import logging
import httpx
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class RestartWebhookService:
    """Service for triggering backend restart via Device Node"""

    def __init__(self):
        # Device Node MCP endpoint (runs on host)
        self.device_node_url = os.getenv(
            "DEVICE_NODE_URL", "http://host.docker.internal:3100"
        )
        self.timeout = float(os.getenv("RESTART_WEBHOOK_TIMEOUT", "30"))
        # Project root on host machine (for docker compose command)
        self.project_root = os.getenv(
            "LOCAL_CORE_PROJECT_ROOT",
            "/Users/shock/Projects_local/workspace/mindscape-ai-local-core",
        )

    def is_configured(self) -> bool:
        """Check if Device Node URL is configured"""
        return bool(self.device_node_url)

    async def notify_restart_required(
        self,
        capability_code: str,
        validation_passed: bool,
        version: str = "1.0.0",
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Request backend restart via Device Node shell capability.

        Only executes if validation_passed is True.

        Args:
            capability_code: The installed capability code
            validation_passed: Whether pre-restart validation passed
            version: Capability version
            extra_data: Additional data for logging

        Returns:
            Result dict with success status and details
        """
        if not self.is_configured():
            return {"sent": False, "reason": "device_node_not_configured"}

        if not validation_passed:
            logger.warning(f"Restart skipped for {capability_code}: validation failed")
            return {"sent": False, "reason": "validation_failed"}

        # MCP tool call format for Device Node
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "shell_execute",
                "arguments": {
                    "command": "docker",
                    "args": ["compose", "restart", "backend"],
                    "cwd": self.project_root,
                    "capability": "docker_admin",
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mindscape-LocalCore/1.0",
            "X-Request-Source": "capability-install",
            "X-Capability-Code": capability_code,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.device_node_url}/mcp", json=mcp_request, headers=headers
                )

            result = response.json()

            if response.status_code >= 200 and response.status_code < 300:
                if result.get("result", {}).get("success", False):
                    logger.info(
                        f"Backend restart triggered via Device Node for {capability_code}"
                    )
                    return {
                        "sent": True,
                        "method": "device_node",
                        "capability": capability_code,
                        "result": result.get("result"),
                    }
                else:
                    error = result.get("error", {}).get("message", "Unknown error")
                    logger.warning(f"Device Node restart failed: {error}")
                    return {
                        "sent": False,
                        "reason": "device_node_error",
                        "error": error,
                    }
            else:
                logger.warning(f"Device Node request failed: {response.status_code}")
                return {
                    "sent": False,
                    "reason": "http_error",
                    "status_code": response.status_code,
                }

        except httpx.TimeoutException:
            logger.error(f"Device Node timeout for {capability_code}")
            return {"sent": False, "reason": "timeout"}
        except httpx.ConnectError:
            logger.warning("Device Node not reachable - is it running on host?")
            return {
                "sent": False,
                "reason": "device_node_unreachable",
                "hint": "Start Device Node on host with: cd device-node && npm run dev",
            }
        except Exception as e:
            logger.error(f"Device Node error: {e}")
            return {"sent": False, "reason": "error", "error": str(e)}


# Singleton instance
_webhook_service: Optional[RestartWebhookService] = None


def get_restart_webhook_service() -> RestartWebhookService:
    """Get singleton webhook service instance"""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = RestartWebhookService()
    return _webhook_service
