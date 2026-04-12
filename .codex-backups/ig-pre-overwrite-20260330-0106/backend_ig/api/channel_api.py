"""
Channel API — IG OAuth channel status endpoint.

Returns connected IG accounts with 4-state display:
  connected / expired / revoked / page_unlinked

Uses CloudRegistryClient for token status inspection.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IG Channels"])


@router.get("/channels")
async def list_channels(
    workspace_id: str = Query(..., description="Workspace ID"),
):
    """List connected IG channels with OAuth status.

    Returns channel_config entries for this workspace with status:
      - connected: token valid, permissions OK
      - expired: token needs refresh
      - revoked: user revoked permissions
      - page_unlinked: IG business account not linked to FB page
    """
    try:
        channels = await _fetch_channel_configs(workspace_id)
        return {
            "status": "success",
            "channels": channels,
            "total": len(channels),
        }
    except Exception as e:
        logger.error("[ChannelAPI] Failed to list channels: %s", e)
        return {
            "status": "error",
            "channels": [],
            "total": 0,
            "error": str(e),
        }


async def _fetch_channel_configs(workspace_id: str) -> List[Dict[str, Any]]:
    """Fetch IG channel configs from cloud registry."""
    results = []

    try:
        # Try to get channel configs from cloud connector
        from app.services.cloud_connector.cloud_registry_client import (
            CloudRegistryClient,
        )

        client = CloudRegistryClient()
        configs = await client.get_channel_configs(
            workspace_id=workspace_id,
            platform="instagram",
        )

        for cfg in configs:
            status = _determine_channel_status(cfg)
            results.append({
                "channel_config_id": cfg.get("id", ""),
                "ig_handle": cfg.get("ig_handle", ""),
                "ig_business_account_id": cfg.get("ig_business_account_id", ""),
                "fb_page_name": cfg.get("fb_page_name", ""),
                "status": status,
                "connected_at": cfg.get("created_at"),
                "last_used_at": cfg.get("last_used_at"),
            })

    except ImportError:
        logger.info("[ChannelAPI] CloudRegistryClient not available (standalone mode)")
    except Exception as e:
        logger.warning("[ChannelAPI] Failed to fetch from cloud registry: %s", e)

    return results


def _determine_channel_status(config: Dict[str, Any]) -> str:
    """Determine 4-state channel status from config."""
    error_code = config.get("error_code", "")
    token_status = config.get("token_status", "")

    if error_code == "invalid_credentials" or token_status == "revoked":
        return "revoked"

    if token_status == "expired" or error_code == "token_expired":
        return "expired"

    if not config.get("ig_business_account_id"):
        return "page_unlinked"

    return "connected"
