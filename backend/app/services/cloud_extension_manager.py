"""
Cloud Extension Manager
Manages multiple cloud playbook providers
"""

import logging
from typing import Dict, Optional, List, Tuple
from backend.app.services.cloud_providers.base import CloudProvider

logger = logging.getLogger(__name__)


class CloudExtensionManager:
    """
    Manages multiple cloud playbook providers

    This allows the system to support multiple cloud providers simultaneously,
    enabling developers to add their own cloud services or use third-party providers.
    """

    _instance: Optional['CloudExtensionManager'] = None

    def __init__(self):
        """Initialize Cloud Extension Manager"""
        if hasattr(self, '_initialized'):
            return
        self.providers: Dict[str, CloudProvider] = {}
        self._initialized = True
        logger.info("CloudExtensionManager initialized")

    @classmethod
    def instance(cls) -> 'CloudExtensionManager':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_provider(self, provider: CloudProvider):
        """
        Register a cloud provider

        Args:
            provider: CloudProvider instance
        """
        provider_id = provider.get_provider_id()
        if provider_id in self.providers:
            logger.warning(f"Provider {provider_id} already registered, overwriting")

        self.providers[provider_id] = provider
        logger.info(f"Registered cloud provider: {provider.get_provider_name()} ({provider_id})")

    def unregister_provider(self, provider_id: str):
        """
        Unregister a cloud provider

        Args:
            provider_id: Provider identifier
        """
        if provider_id in self.providers:
            del self.providers[provider_id]
            logger.info(f"Unregistered cloud provider: {provider_id}")

    def get_provider(self, provider_id: str) -> Optional[CloudProvider]:
        """
        Get provider by ID

        Args:
            provider_id: Provider identifier

        Returns:
            CloudProvider instance or None
        """
        return self.providers.get(provider_id)

    def list_providers(self) -> List[Dict]:
        """
        List all registered providers

        Returns:
            List of provider info dicts
        """
        return [
            {
                "provider_id": provider.get_provider_id(),
                "name": provider.get_provider_name(),
                "description": provider.get_provider_description(),
                "configured": provider.is_configured(),
                "config_schema": provider.get_config_schema()
            }
            for provider in self.providers.values()
        ]

    async def get_playbook(
        self,
        provider_id: str,
        capability_code: str,
        playbook_code: str,
        locale: str = "en"
    ) -> Optional[Dict]:
        """
        Get playbook from specific provider

        Args:
            provider_id: Provider identifier
            capability_code: Capability pack code
            playbook_code: Playbook code
            locale: Locale code

        Returns:
            Playbook data dict or None
        """
        provider = self.get_provider(provider_id)
        if not provider:
            logger.warning(f"Provider {provider_id} not found")
            return None

        if not provider.is_configured():
            logger.debug(f"Provider {provider_id} not configured")
            return None

        try:
            return await provider.get_playbook(capability_code, playbook_code, locale)
        except Exception as e:
            logger.error(f"Failed to get playbook from provider {provider_id}: {e}")
            return None

    async def get_playbook_from_any_provider(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str = "en",
        preferred_provider: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get playbook from any configured provider

        Tries providers in order:
        1. Preferred provider (if specified and configured)
        2. All other configured providers

        Args:
            capability_code: Capability pack code
            playbook_code: Playbook code
            locale: Locale code
            preferred_provider: Preferred provider ID (optional)

        Returns:
            Playbook data dict or None
        """
        # Try preferred provider first
        if preferred_provider:
            provider = self.get_provider(preferred_provider)
            if provider and provider.is_configured():
                result = await self.get_playbook(
                    preferred_provider, capability_code, playbook_code, locale
                )
                if result:
                    return result

        # Try all other configured providers
        for provider_id, provider in self.providers.items():
            if preferred_provider and provider_id == preferred_provider:
                continue  # Already tried

            if provider.is_configured():
                result = await self.get_playbook(
                    provider_id, capability_code, playbook_code, locale
                )
                if result:
                    return result

        return None

    async def test_provider_connection(self, provider_id: str) -> Tuple[bool, str]:
        """
        Test connection to a provider

        Args:
            provider_id: Provider identifier

        Returns:
            Tuple of (success: bool, message: str)
        """
        provider = self.get_provider(provider_id)
        if not provider:
            return False, f"Provider {provider_id} not found"

        if not provider.is_configured():
            return False, "Provider not configured"

        try:
            return await provider.test_connection()
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

