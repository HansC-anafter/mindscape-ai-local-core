"""
Restart Webhook Service

Sends validated restart notifications to external orchestrators.
Only triggers after validation passes.
"""

import os
import logging
import httpx
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class RestartWebhookService:
    """Service for notifying orchestrators about restart requirements"""

    def __init__(self):
        self.webhook_url = os.getenv("RESTART_WEBHOOK_URL")
        self.webhook_secret = os.getenv("RESTART_WEBHOOK_SECRET", "")
        self.timeout = float(os.getenv("RESTART_WEBHOOK_TIMEOUT", "10"))

    def is_configured(self) -> bool:
        """Check if webhook is configured"""
        return bool(self.webhook_url)

    async def notify_restart_required(
        self,
        capability_code: str,
        validation_passed: bool,
        version: str = "1.0.0",
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send restart notification to configured webhook.

        Only sends if validation_passed is True.

        Args:
            capability_code: The installed capability code
            validation_passed: Whether pre-restart validation passed
            version: Capability version
            extra_data: Additional data to include

        Returns:
            Result dict with success status and details
        """
        if not self.is_configured():
            return {"sent": False, "reason": "webhook_not_configured"}

        if not validation_passed:
            logger.warning(
                f"Restart webhook skipped for {capability_code}: validation failed"
            )
            return {"sent": False, "reason": "validation_failed"}

        payload = {
            "action": "restart_required",
            "capability": capability_code,
            "version": version,
            "validated": True,
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

        if extra_data:
            payload["extra"] = extra_data

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mindscape-LocalCore/1.0",
        }

        if self.webhook_secret:
            headers["X-Webhook-Secret"] = self.webhook_secret

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url, json=payload, headers=headers
                )

            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Restart webhook sent successfully for {capability_code}")
                return {
                    "sent": True,
                    "status_code": response.status_code,
                    "capability": capability_code,
                }
            else:
                logger.warning(
                    f"Restart webhook failed: {response.status_code} - {response.text}"
                )
                return {
                    "sent": False,
                    "reason": "webhook_error",
                    "status_code": response.status_code,
                    "error": response.text[:200],
                }

        except httpx.TimeoutException:
            logger.error(f"Restart webhook timeout for {capability_code}")
            return {"sent": False, "reason": "timeout"}
        except Exception as e:
            logger.error(f"Restart webhook error: {e}")
            return {"sent": False, "reason": "error", "error": str(e)}


# Singleton instance
_webhook_service: Optional[RestartWebhookService] = None


def get_restart_webhook_service() -> RestartWebhookService:
    """Get singleton webhook service instance"""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = RestartWebhookService()
    return _webhook_service
