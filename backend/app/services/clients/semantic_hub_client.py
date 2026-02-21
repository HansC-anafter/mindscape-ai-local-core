"""
Semantic-Hub Client

Handles Semantic-Hub integration including:
- Orchestrator invocation
- Chain execution
- WebSocket event subscription
"""

import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, List
from urllib.parse import urljoin
import json

logger = logging.getLogger(__name__)


class SemanticHubClient:
    """
    Semantic-Hub Client

    Connects to Semantic-Hub for:
    - Agent task execution
    - Chain invocation
    - Event subscription
    """

    def __init__(self, base_url: str, api_token: Optional[str] = None):
        """
        Initialize Semantic-Hub client

        Args:
            base_url: Semantic-Hub API URL
            api_token: API Token
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def execute_agent(
        self,
        agent_type: str,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute agent task

        Args:
            agent_type: Agent type (e.g., "planner", "writer", "coach")
            task: Task description
            context: Context information (Profile, Intents, etc.)
            tenant_id: Tenant ID (optional)

        Returns:
            Execution result including execution_id and initial response

        Raises:
            Exception: Execution failed
        """
        url = urljoin(self.base_url, "/api/v1/orchestrator/execute")
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        payload = {
            "agent_type": agent_type,
            "task": task,
            "context": context or {},
            "tenant_id": tenant_id,
        }

        try:
            session = await self._get_session()
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Semantic-Hub execution failed: {response.status} - {error_text}"
                    )

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"Semantic-Hub connection error: {e}")
            raise Exception(f"Failed to connect to Semantic-Hub: {str(e)}")

    async def get_execution_result(self, execution_id: str) -> Dict[str, Any]:
        """
        Get execution result

        Args:
            execution_id: Execution ID

        Returns:
            Execution result and status

        Raises:
            Exception: Query failed
        """
        url = urljoin(self.base_url, f"/api/v1/orchestrator/executions/{execution_id}")
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    raise Exception(f"Execution not found: {execution_id}")
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to get execution result: {response.status} - {error_text}"
                    )

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"Semantic-Hub connection error: {e}")
            raise Exception(f"Failed to connect to Semantic-Hub: {str(e)}")

    async def continue_execution(
        self, execution_id: str, user_message: str
    ) -> Dict[str, Any]:
        """
        Continue execution with multi-turn dialogue

        Args:
            execution_id: Execution ID
            user_message: User message

        Returns:
            AI response and execution status

        Raises:
            Exception: Execution failed
        """
        url = urljoin(
            self.base_url, f"/api/v1/orchestrator/executions/{execution_id}/continue"
        )
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        payload = {"user_message": user_message}

        try:
            session = await self._get_session()
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(
                        f"Continue execution failed: {response.status} - {error_text}"
                    )

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"Semantic-Hub connection error: {e}")
            raise Exception(f"Failed to connect to Semantic-Hub: {str(e)}")

    async def subscribe_events(
        self, execution_id: str, callback: Callable[[Dict[str, Any]], None]
    ):
        """
        Subscribe to execution events via WebSocket

        Args:
            execution_id: Execution ID
            callback: Event callback function

        Note:
            Long-lived connection until execution completes or manually closed
        """
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = urljoin(
            ws_url, f"/api/v1/orchestrator/executions/{execution_id}/events"
        )

        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            session = await self._get_session()
            async with session.ws_connect(ws_url, headers=headers) as ws:
                logger.info(f"WebSocket connected for execution: {execution_id}")

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            callback(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse WebSocket message: {e}")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
                        break
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                    ):
                        logger.info("WebSocket connection closed")
                        break

        except aiohttp.ClientError as e:
            logger.error(f"WebSocket connection error: {e}")
            raise Exception(f"Failed to subscribe to events: {str(e)}")

    async def health_check(self) -> bool:
        """
        Check Semantic-Hub health status

        Returns:
            Whether service is healthy
        """
        url = urljoin(self.base_url, "/health")

        try:
            session = await self._get_session()
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
        except Exception:
            return False

    def is_configured(self) -> bool:
        """Check if client is configured"""
        return bool(self.base_url and self.api_token)
