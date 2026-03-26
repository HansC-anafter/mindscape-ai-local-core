"""
Cloud Connector

Manages WebSocket connection to Cloud control plane for
distributed execution. Acts as the local-core side of the
Bridge architecture, enabling remote execution dispatch.

This service is optional and must be explicitly enabled via
CLOUD_CONNECTOR_ENABLED=true environment variable.
"""

import asyncio
import logging
import os
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class CloudConnector:
    """Manages connectivity between local-core and cloud control plane.

    Provides HTTP-based communication with the cloud execution API.
    WebSocket-based real-time event streaming is handled separately
    by the executor WS connection.

    This connector is responsible for:
    - Dispatching execution requests to cloud control plane
    - Polling execution status and results
    - Cancelling remote executions
    """

    def __init__(self):
        self.cloud_api_url = os.getenv("CLOUD_API_URL", "http://localhost:8000")
        self.device_id = os.getenv("DEVICE_ID", "")
        self.api_key = os.getenv("CLOUD_API_KEY", "")
        self._connected = False
        self._http_client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> None:
        """Initialize connection to cloud control plane."""
        self._http_client = httpx.AsyncClient(
            base_url=self.cloud_api_url,
            headers={
                "X-Device-ID": self.device_id,
                "Authorization": f"Bearer {self.api_key}",
            },
            timeout=30.0,
        )
        self._connected = True
        logger.info(
            "Cloud Connector connected: url=%s device=%s",
            self.cloud_api_url,
            self.device_id,
        )

    async def disconnect(self) -> None:
        """Close connection to cloud control plane."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._connected = False
        logger.info("Cloud Connector disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._http_client is not None

    async def start_remote_execution(
        self,
        tenant_id: str,
        playbook_code: str,
        request_payload: Dict[str, Any],
        workspace_id: Optional[str] = None,
        capability_code: Optional[str] = None,
        execution_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        job_type: str = "playbook",
        callback_payload: Optional[Dict[str, Any]] = None,
        target_device_id: Optional[str] = None,
        site_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch execution request to cloud control plane.

        Args:
            tenant_id: Tenant identifier for cloud routing
            playbook_code: Playbook to execute
            request_payload: Execution input data
            workspace_id: Optional workspace context
            capability_code: Optional capability identifier

        Returns:
            Cloud execution record with id and state

        Raises:
            ConnectionError: If not connected to cloud
            httpx.HTTPStatusError: On API failure
        """
        if not self.is_connected:
            raise ConnectionError("Cloud Connector not connected")

        governance = (
            request_payload.get("_governance", {})
            if isinstance(request_payload, dict)
            and isinstance(request_payload.get("_governance"), dict)
            else {}
        )
        resolved_site_key = site_key or governance.get("site_key") or os.getenv(
            "SITE_KEY"
        ) or tenant_id
        response = await self._http_client.post(
            "/api/v1/executions",
            json={
                "tenant_id": tenant_id,
                "execution_id": execution_id,
                "trace_id": trace_id,
                "job_type": job_type,
                "playbook_code": playbook_code,
                "request_payload": request_payload,
                "workspace_id": workspace_id,
                "capability_code": capability_code,
                "device_id": target_device_id,
                "site_key": resolved_site_key,
                "callback_payload": callback_payload,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_runtime_availability(
        self,
        *,
        site_key: str,
        target_device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Probe runtime availability from the cloud control plane."""
        if not self.is_connected:
            raise ConnectionError("Cloud Connector not connected")

        params: Dict[str, Any] = {"site_key": site_key}
        if isinstance(target_device_id, str) and target_device_id.strip():
            params["device_id"] = target_device_id.strip()

        response = await self._http_client.get(
            "/api/v1/executions/availability",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_execution_status(
        self,
        execution_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Poll execution status from cloud control plane.

        Args:
            execution_id: Cloud execution identifier
            tenant_id: Optional tenant filter

        Returns:
            Execution record with current state
        """
        if not self.is_connected:
            raise ConnectionError("Cloud Connector not connected")

        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id

        response = await self._http_client.get(
            f"/api/v1/executions/{execution_id}",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_remote_execution(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compatibility alias for newer CloudConnector call sites."""
        return await self.get_execution_status(execution_id, tenant_id=tenant_id)

    async def get_execution_result(
        self,
        execution_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve execution result from cloud control plane.

        Args:
            execution_id: Cloud execution identifier
            tenant_id: Optional tenant filter

        Returns:
            Execution result payload
        """
        if not self.is_connected:
            raise ConnectionError("Cloud Connector not connected")

        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id

        response = await self._http_client.get(
            f"/api/v1/executions/{execution_id}/result",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def get_remote_execution_result(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compatibility alias for newer CloudConnector call sites."""
        return await self.get_execution_result(execution_id, tenant_id=tenant_id)

    async def wait_for_remote_execution_terminal_result(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
        timeout_seconds: float = 900.0,
        poll_interval_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """Poll until a remote execution reaches a terminal state."""
        terminal_states = {"completed", "failed", "cancelled", "timeout"}
        started_at = asyncio.get_running_loop().time()

        while True:
            execution = await self.get_remote_execution(
                execution_id,
                tenant_id=tenant_id,
            )
            state = str(execution.get("state") or "").strip().lower()
            if state in terminal_states:
                result = await self.get_remote_execution_result(
                    execution_id,
                    tenant_id=tenant_id,
                )
                return {
                    "status": state,
                    "execution": execution,
                    "result_payload": result.get("result_payload"),
                    "error_message": result.get("error_message"),
                    "completed_at": result.get("completed_at"),
                    "callback_delivered_at": (
                        result.get("callback_delivered_at")
                        or execution.get("callback_delivered_at")
                    ),
                    "callback_error": (
                        result.get("callback_error") or execution.get("callback_error")
                    ),
                }

            elapsed_seconds = asyncio.get_running_loop().time() - started_at
            if elapsed_seconds >= max(1.0, float(timeout_seconds)):
                raise TimeoutError(
                    f"Timed out waiting for remote execution {execution_id} "
                    f"after {timeout_seconds:.1f}s"
                )

            await asyncio.sleep(max(0.1, float(poll_interval_seconds)))

    async def cancel_execution(
        self,
        execution_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Cancel a remote execution.

        Args:
            execution_id: Cloud execution identifier
            tenant_id: Optional tenant filter

        Returns:
            Updated execution record
        """
        if not self.is_connected:
            raise ConnectionError("Cloud Connector not connected")

        params = {}
        if tenant_id:
            params["tenant_id"] = tenant_id

        response = await self._http_client.post(
            f"/api/v1/executions/{execution_id}/cancel",
            params=params,
        )
        response.raise_for_status()
        return response.json()
