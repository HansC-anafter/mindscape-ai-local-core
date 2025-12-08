"""
Redis Cache Service

Provides Redis-based caching for tool registry and other services.
"""

import json
import os
import logging
from typing import Optional, Any, Dict
import redis
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)


class RedisCacheService:
    """
    Redis-based cache service for tool registry and other cached data.

    Provides graceful degradation - if Redis is unavailable, cache operations
    silently fail and fall back to direct queries.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        db: Optional[int] = None,
        enabled: Optional[bool] = None,
        default_ttl: int = 600  # 10 minutes default TTL
    ):
        """
        Initialize Redis cache service.

        Args:
            host: Redis host (default: from REDIS_HOST env or 'redis')
            port: Redis port (default: from REDIS_PORT env or 6379)
            password: Redis password (default: from REDIS_PASSWORD env or None)
            db: Redis database number (default: from REDIS_DB env or 0)
            enabled: Whether Redis is enabled (default: from REDIS_ENABLED env or True)
            default_ttl: Default TTL in seconds (default: 600)
        """
        # Get configuration from environment or parameters
        self.host = host or os.getenv("REDIS_HOST", "redis")
        self.port = int(port or os.getenv("REDIS_PORT", "6379"))
        self.password = password if password is not None else os.getenv("REDIS_PASSWORD")
        self.db = int(db if db is not None else os.getenv("REDIS_DB", "0"))
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("REDIS_ENABLED", "true").lower() == "true"
        )
        self.default_ttl = default_ttl

        self._client: Optional[redis.Redis] = None
        self._available = False

        if self.enabled:
            try:
                self._connect()
            except Exception as e:
                logger.warning(f"Redis connection failed, cache disabled: {e}")
                self._available = False

    def _connect(self):
        """Establish connection to Redis."""
        if not self.enabled:
            return

        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
            # Test connection
            self._client.ping()
            self._available = True
            logger.info(
                f"Redis cache connected: {self.host}:{self.port}/{self.db}"
            )
        except (ConnectionError, TimeoutError, Exception) as e:
            logger.warning(f"Redis connection failed: {e}")
            self._available = False
            self._client = None

    def _ensure_connected(self) -> bool:
        """Ensure Redis connection is available."""
        if not self.enabled:
            return False

        if not self._available or not self._client:
            try:
                self._connect()
            except Exception:
                return False

        # Test connection
        try:
            self._client.ping()
            return True
        except Exception:
            self._available = False
            return False

    def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value as string, or None if not found or unavailable
        """
        if not self._ensure_connected():
            return None

        try:
            value = self._client.get(key)
            if value:
                logger.debug(f"Cache hit: {key}")
            return value
        except Exception as e:
            logger.debug(f"Cache get failed for {key}: {e}")
            return None

    def set(
        self, key: str, value: str, ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be string)
            ttl: Time to live in seconds (default: self.default_ttl)

        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False

        try:
            ttl = ttl if ttl is not None else self.default_ttl
            self._client.setex(key, ttl, value)
            logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.debug(f"Cache set failed for {key}: {e}")
            return False

    def get_json(self, key: str) -> Optional[Any]:
        """
        Get JSON value from cache.

        Args:
            key: Cache key

        Returns:
            Deserialized JSON object, or None if not found or unavailable
        """
        value = self.get(key)
        if value is None:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"Failed to deserialize JSON from cache key: {key}")
            return None

    def set_json(
        self, key: str, value: Any, ttl: Optional[int] = None
    ) -> bool:
        """
        Set JSON value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (default: self.default_ttl)

        Returns:
            True if successful, False otherwise
        """
        try:
            json_value = json.dumps(value)
            return self.set(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize JSON for cache key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        if not self._ensure_connected():
            return False

        try:
            self._client.delete(key)
            logger.debug(f"Cache delete: {key}")
            return True
        except Exception as e:
            logger.debug(f"Cache delete failed for {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Redis key pattern (e.g., "tool_registry:workspace:*")

        Returns:
            Number of keys deleted
        """
        if not self._ensure_connected():
            return 0

        try:
            keys = self._client.keys(pattern)
            if keys:
                deleted = self._client.delete(*keys)
                logger.debug(f"Cache delete pattern: {pattern} ({deleted} keys)")
                return deleted
            return 0
        except Exception as e:
            logger.debug(f"Cache delete pattern failed for {pattern}: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        if not self._ensure_connected():
            return False

        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        """Check if Redis cache is available."""
        return self._available and self._ensure_connected()


# Global cache instance (singleton)
_cache_instance: Optional[RedisCacheService] = None


def get_cache_service() -> RedisCacheService:
    """
    Get or create global cache service instance.

    Returns:
        RedisCacheService instance
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCacheService()
    return _cache_instance

