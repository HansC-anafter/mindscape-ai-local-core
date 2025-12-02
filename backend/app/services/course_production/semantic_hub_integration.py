"""
Semantic Hub Integration for Course Production

Helper functions to get and use Semantic Hub client for course production services
"""

import os
import logging
from typing import Optional
from ...services.clients.semantic_hub_client import SemanticHubClient

logger = logging.getLogger(__name__)

# Global client instance
_semantic_hub_client: Optional[SemanticHubClient] = None


def get_semantic_hub_client() -> Optional[SemanticHubClient]:
    """
    Get Semantic Hub client instance

    Returns:
        SemanticHubClient instance or None if not configured
    """
    global _semantic_hub_client

    if _semantic_hub_client is not None:
        return _semantic_hub_client

    # Get configuration from environment
    semantic_hub_url = os.getenv("SEMANTIC_HUB_URL") or os.getenv("SEMANTIC_HUB_API_URL")
    api_token = os.getenv("SEMANTIC_HUB_API_TOKEN") or os.getenv("API_TOKEN")

    if not semantic_hub_url:
        logger.warning("Semantic Hub URL not configured. Course production training features will be unavailable.")
        return None

    _semantic_hub_client = SemanticHubClient(
        base_url=semantic_hub_url,
        api_token=api_token
    )

    logger.info(f"Semantic Hub client initialized: {semantic_hub_url}")
    return _semantic_hub_client


def is_semantic_hub_available() -> bool:
    """Check if Semantic Hub is configured and available"""
    client = get_semantic_hub_client()
    return client is not None and client.is_configured()
