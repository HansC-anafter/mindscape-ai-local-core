"""
Site-Hub External Backend Implementation

Official ExternalBackend implementation for Site-Hub.
Implements the ExternalBackend protocol, providing standardized HTTP API interface.
"""

import aiohttp
import asyncio
import logging
import time
import uuid
import hashlib
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
from .external_backend import ExternalBackend

logger = logging.getLogger(__name__)


class SiteHubBackend(ExternalBackend):
    """
    Site-Hub Official ExternalBackend Implementation

    Implements ExternalBackend protocol, providing standardized HTTP API interface.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Site-Hub backend

        Args:
            config: {
                "base_url": str,      # Site-Hub API base URL
                "api_key": str,        # API authentication key
                "timeout": float       # Timeout in seconds (default 1.5)
            }
        """
        self.base_url = config.get("base_url", "").rstrip("/")
        self.api_key = config.get("api_key")
        self.timeout = config.get("timeout", 1.5)

        # Circuit Breaker mechanism
        self.circuit_breaker: Dict[str, Dict[str, Any]] = {}
        self.circuit_breaker_threshold = 3
        self.circuit_breaker_timeout = 300  # 5 minutes

        # Cache mechanism
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = 300  # 5 minutes

        # HTTP session (lazy initialization)
        self._session: Optional[aiohttp.ClientSession] = None

        logger.info(f"Site-Hub backend initialized: base_url={self.base_url}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def retrieve_context(
        self,
        workspace_id: str,
        message: str,
        workspace_context: Dict[str, Any],
        profile_id: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Call Site-Hub context retrieval endpoint

        Args:
            workspace_id: Workspace identifier
            message: User query text
            workspace_context: Workspace context from Mindscape
            profile_id: User profile identifier
            session_id: Session identifier

        Returns:
            {
                "success": bool,
                "retrieved_context": str,
                "retrieved_snippets": List[Dict[str, Any]],
                "retrieval_metadata": Dict[str, Any]
            }
        """
        # 1. Check Circuit Breaker
        breaker_key = f"{workspace_id}:{session_id}"
        if self._is_circuit_open(breaker_key):
            logger.warning(f"Circuit breaker open for {breaker_key}, skipping retrieval")
            return {
                "success": False,
                "retrieved_context": "",
                "retrieved_snippets": [],
                "retrieval_metadata": {"error": "circuit_breaker_open"}
            }

        # 2. Check cache
        cache_key = self._generate_cache_key(workspace_id, message)
        cached_result = self._get_cache(cache_key)
        if cached_result:
            logger.info(f"Cache hit for {cache_key}")
            return cached_result

        # 3. Build request
        request = {
            "request_id": str(uuid.uuid4()),
            "user_id": profile_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
            "message": message,
            "workspace_context": workspace_context,
            "retrieval_config": {
                "max_iterations": 3,
                "min_relevance_threshold": 0.6,
                "max_results": 10,
                "enable_agentic_rag": True,
                "fast_mode": True
            }
        }

        # 4. Call Site-Hub API
        try:
            session = await self._get_session()
            url = urljoin(self.base_url, "/v1/context/retrieve")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with session.post(url, json=request, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Site-Hub API error: {response.status} - {error_text}")

                result = await response.json()

                # 5. Update Circuit Breaker (success)
                self._record_success(breaker_key)

                # 6. Write to cache
                self._set_cache(cache_key, result)

                logger.info(f"✅ Site-Hub retrieval completed: {len(result.get('retrieved_snippets', []))} snippets")
                return result

        except aiohttp.ClientError as e:
            # 7. Update Circuit Breaker (failure)
            self._record_failure(breaker_key)
            logger.warning(f"Site-Hub retrieval failed (client error): {e}")
            return {
                "success": False,
                "retrieved_context": "",
                "retrieved_snippets": [],
                "retrieval_metadata": {"error": str(e)}
            }
        except asyncio.TimeoutError as e:
            # Timeout
            self._record_failure(breaker_key)
            logger.warning(f"Site-Hub retrieval timeout: {e}")
            return {
                "success": False,
                "retrieved_context": "",
                "retrieved_snippets": [],
                "retrieval_metadata": {"error": "timeout"}
            }
        except Exception as e:
            # 7. Update Circuit Breaker (failure)
            self._record_failure(breaker_key)
            logger.warning(f"Site-Hub retrieval failed: {e}")
            return {
                "success": False,
                "retrieved_context": "",
                "retrieved_snippets": [],
                "retrieval_metadata": {"error": str(e)}
            }

    async def list_capabilities(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Call Site-Hub capabilities list endpoint

        Args:
            workspace_id: Workspace identifier

        Returns:
            {
                "success": bool,
                "capabilities": List[Dict[str, Any]]
            }
        """
        try:
            session = await self._get_session()
            url = urljoin(self.base_url, f"/v1/workspaces/{workspace_id}/capabilities")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(f"Site-Hub list_capabilities failed: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "capabilities": []
                    }

                result = await response.json()
                return {
                    "success": True,
                    "capabilities": result.get("capabilities", [])
                }

        except Exception as e:
            logger.warning(f"Site-Hub list_capabilities failed: {e}")
            return {
                "success": False,
                "capabilities": []
            }

    async def sync_artifact(
        self,
        workspace_id: str,
        artifact: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call Site-Hub artifact sync endpoint

        Args:
            workspace_id: Workspace identifier
            artifact: Artifact data

        Returns:
            {
                "success": bool,
                "artifact_id": str,
                "synced_at": str
            }
        """
        try:
            session = await self._get_session()
            url = urljoin(self.base_url, f"/v1/workspaces/{workspace_id}/artifacts/sync")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {"artifact": artifact}

            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(f"Site-Hub sync_artifact failed: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "artifact_id": artifact.get("artifact_id", ""),
                        "synced_at": None
                    }

                result = await response.json()
                return result

        except Exception as e:
            logger.warning(f"Site-Hub sync_artifact failed: {e}")
            return {
                "success": False,
                "artifact_id": artifact.get("artifact_id", ""),
                "synced_at": None
            }

    # Circuit Breaker and Cache mechanism (internal methods)

    def _is_circuit_open(self, breaker_key: str) -> bool:
        """Check if Circuit Breaker is open"""
        if breaker_key not in self.circuit_breaker:
            return False
        breaker_state = self.circuit_breaker[breaker_key]
        if breaker_state["status"] == "open":
            if (time.time() - breaker_state["opened_at"]) > self.circuit_breaker_timeout:
                breaker_state["status"] = "half_open"
                breaker_state["failure_count"] = 0
                return False
            return True
        return False

    def _record_success(self, breaker_key: str):
        """Record success, reset Circuit Breaker"""
        if breaker_key in self.circuit_breaker:
            breaker_state = self.circuit_breaker[breaker_key]
            if breaker_state["status"] == "half_open":
                breaker_state["status"] = "closed"
            breaker_state["failure_count"] = 0

    def _record_failure(self, breaker_key: str):
        """Record failure, update Circuit Breaker"""
        if breaker_key not in self.circuit_breaker:
            self.circuit_breaker[breaker_key] = {
                "status": "closed",
                "failure_count": 0,
                "opened_at": 0
            }
        breaker_state = self.circuit_breaker[breaker_key]
        breaker_state["failure_count"] += 1
        if breaker_state["failure_count"] >= self.circuit_breaker_threshold:
            breaker_state["status"] = "open"
            breaker_state["opened_at"] = time.time()
            logger.warning(f"Circuit breaker opened for {breaker_key}")

    def _generate_cache_key(self, workspace_id: str, message: str) -> str:
        """Generate cache key"""
        message_hash = hashlib.md5(message.encode()).hexdigest()[:8]
        return f"rag:{workspace_id}:{message_hash}"

    def _get_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cache"""
        if cache_key in self.cache:
            cached_item = self.cache[cache_key]
            if (time.time() - cached_item["timestamp"]) < self.cache_ttl:
                return cached_item["data"]
            else:
                del self.cache[cache_key]
        return None

    def _set_cache(self, cache_key: str, data: Dict[str, Any]):
        """Set cache"""
        self.cache[cache_key] = {
            "data": data,
            "timestamp": time.time()
        }


def create_backend(options: Dict[str, Any]) -> ExternalBackend:
    """
    Create Site-Hub backend instance

    This function is called by the dynamic loader to create a SiteHubBackend instance.

    Args:
        options: {
            "base_url": str,      # Site-Hub API base URL
            "api_key": str,        # API authentication key
            "timeout": float       # Timeout in seconds (default 1.5)
        }

    Returns:
        SiteHubBackend instance
    """
    return SiteHubBackend(options)
