"""
Cloud Provider Base Interface
Abstract base class for all cloud playbook providers
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class CloudProvider(ABC):
    """
    Abstract base class for cloud playbook providers

    This interface allows developers to create custom cloud providers
    for distributing playbooks. Each provider can have its own
    authentication method, API structure, and configuration.
    """

    @abstractmethod
    def get_provider_id(self) -> str:
        """
        Return unique provider identifier

        Returns:
            Unique string identifier (e.g., "mindscape_official", "my_custom_cloud")
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Return human-readable provider name

        Returns:
            Display name for the provider
        """
        pass

    @abstractmethod
    def get_provider_description(self) -> str:
        """
        Return provider description

        Returns:
            Description of what this provider offers
        """
        pass

    @abstractmethod
    async def get_playbook(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str = "en"
    ) -> Optional[Dict]:
        """
        Download playbook from this provider

        Args:
            capability_code: Capability pack code (e.g., "web_generation")
            playbook_code: Playbook code (e.g., "page_outline")
            locale: Locale code (e.g., "en", "zh-TW")

        Returns:
            Playbook data dict with 'content' field, or None if not available
        """
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Check if provider is properly configured

        Returns:
            True if provider has all required configuration
        """
        pass

    @abstractmethod
    async def test_connection(self) -> Tuple[bool, str]:
        """
        Test connection to provider

        Returns:
            Tuple of (success: bool, message: str)
        """
        pass

    def get_config_schema(self) -> Dict:
        """
        Return configuration schema for this provider

        This is used by UI to generate configuration forms

        Returns:
            Dict with configuration fields and their types
        """
        return {
            "fields": [],
            "required": []
        }

    def validate_config(self, config: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate provider configuration

        Args:
            config: Configuration dict

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        return True, None

