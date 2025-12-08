"""
Tool Registry Cache Service

Provides Redis-based caching specifically for tool registry queries.
Caches formatted tool lists to reduce database queries and token usage.
"""

import logging
from typing import Optional, List, Dict, Any

from backend.app.services.cache.redis_cache import get_cache_service

logger = logging.getLogger(__name__)


class ToolRegistryCache:
    """
    Cache service specifically for tool registry queries.

    Caches:
    1. Tool list JSON (for re-formatting)
    2. Formatted tool list strings (for direct use in prompts)
    3. Tool IDs list (for quick validation)
    """

    CACHE_PREFIX = "tool_registry"
    DEFAULT_TTL = 600  # 10 minutes

    def __init__(self, cache_service=None):
        """
        Initialize tool registry cache.

        Args:
            cache_service: Optional RedisCacheService instance (default: global instance)
        """
        self.cache = cache_service or get_cache_service()
        self.ttl = self.DEFAULT_TTL

    def _get_tools_json_key(self, workspace_id: str, profile_id: Optional[str] = None) -> str:
        """Generate cache key for tools JSON."""
        if profile_id:
            return f"{self.CACHE_PREFIX}:workspace:{workspace_id}:profile:{profile_id}:tools_json"
        return f"{self.CACHE_PREFIX}:workspace:{workspace_id}:tools_json"

    def _get_tools_str_key(self, workspace_id: str, profile_id: Optional[str] = None) -> str:
        """Generate cache key for formatted tools string."""
        if profile_id:
            return f"{self.CACHE_PREFIX}:workspace:{workspace_id}:profile:{profile_id}:tools_str"
        return f"{self.CACHE_PREFIX}:workspace:{workspace_id}:tools_str"

    def _get_tool_ids_key(self, workspace_id: str, profile_id: Optional[str] = None) -> str:
        """Generate cache key for tool IDs list."""
        if profile_id:
            return f"{self.CACHE_PREFIX}:workspace:{workspace_id}:profile:{profile_id}:tool_ids"
        return f"{self.CACHE_PREFIX}:workspace:{workspace_id}:tool_ids"

    def get_tools_json(
        self,
        workspace_id: str,
        profile_id: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached tools JSON.

        Args:
            workspace_id: Workspace ID
            profile_id: Optional profile ID

        Returns:
            Cached tools list as JSON, or None if not cached
        """
        key = self._get_tools_json_key(workspace_id, profile_id)
        cached = self.cache.get_json(key)
        if cached:
            logger.debug(f"Tool list JSON cache hit for workspace {workspace_id}")
        return cached

    def cache_tools_json(
        self,
        workspace_id: str,
        tools: List[Dict[str, Any]],
        profile_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache tools JSON.

        Args:
            workspace_id: Workspace ID
            tools: Tools list to cache
            profile_id: Optional profile ID
            ttl: Optional TTL override

        Returns:
            True if cached successfully
        """
        key = self._get_tools_json_key(workspace_id, profile_id)
        return self.cache.set_json(key, tools, ttl or self.ttl)

    def get_tools_str(
        self,
        workspace_id: str,
        profile_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get cached formatted tools string.

        Args:
            workspace_id: Workspace ID
            profile_id: Optional profile ID

        Returns:
            Cached formatted tools string, or None if not cached
        """
        key = self._get_tools_str_key(workspace_id, profile_id)
        cached = self.cache.get(key)
        if cached:
            logger.debug(f"Tool list string cache hit for workspace {workspace_id}")
        return cached

    def cache_tools_str(
        self,
        workspace_id: str,
        tools_str: str,
        profile_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache formatted tools string.

        Args:
            workspace_id: Workspace ID
            tools_str: Formatted tools string to cache
            profile_id: Optional profile ID
            ttl: Optional TTL override

        Returns:
            True if cached successfully
        """
        key = self._get_tools_str_key(workspace_id, profile_id)
        return self.cache.set(key, tools_str, ttl or self.ttl)

    def get_tool_ids(
        self,
        workspace_id: str,
        profile_id: Optional[str] = None
    ) -> Optional[List[str]]:
        """
        Get cached tool IDs list.

        Args:
            workspace_id: Workspace ID
            profile_id: Optional profile ID

        Returns:
            Cached tool IDs list, or None if not cached
        """
        key = self._get_tool_ids_key(workspace_id, profile_id)
        cached = self.cache.get_json(key)
        return cached

    def cache_tool_ids(
        self,
        workspace_id: str,
        tool_ids: List[str],
        profile_id: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache tool IDs list.

        Args:
            workspace_id: Workspace ID
            tool_ids: Tool IDs list to cache
            profile_id: Optional profile ID
            ttl: Optional TTL override

        Returns:
            True if cached successfully
        """
        key = self._get_tool_ids_key(workspace_id, profile_id)
        return self.cache.set_json(key, tool_ids, ttl or self.ttl)

    def invalidate_workspace_cache(
        self,
        workspace_id: str,
        profile_id: Optional[str] = None
    ) -> int:
        """
        Invalidate all cache for a workspace.

        Args:
            workspace_id: Workspace ID
            profile_id: Optional profile ID (if provided, only invalidate for this profile)

        Returns:
            Number of keys deleted
        """
        if profile_id:
            pattern = f"{self.CACHE_PREFIX}:workspace:{workspace_id}:profile:{profile_id}:*"
        else:
            pattern = f"{self.CACHE_PREFIX}:workspace:{workspace_id}:*"

        deleted = self.cache.delete_pattern(pattern)
        if deleted > 0:
            logger.info(f"Invalidated {deleted} cache keys for workspace {workspace_id}")
        return deleted

    def invalidate_all_tool_cache(self) -> int:
        """
        Invalidate all tool registry cache.

        Returns:
            Number of keys deleted
        """
        pattern = f"{self.CACHE_PREFIX}:*"
        deleted = self.cache.delete_pattern(pattern)
        if deleted > 0:
            logger.info(f"Invalidated {deleted} tool registry cache keys")
        return deleted


# Global cache instance (singleton)
_cache_instance: Optional[ToolRegistryCache] = None


def get_tool_registry_cache() -> ToolRegistryCache:
    """
    Get or create global tool registry cache instance.

    Returns:
        ToolRegistryCache instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ToolRegistryCache()
    return _cache_instance

