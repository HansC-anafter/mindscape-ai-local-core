"""
Remote execution HTTP client for the cloud connector.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import httpx

from .connector_config import resolve_execution_control_base_url

BaseUrlResolver = Callable[[], Optional[str]]


class RemoteExecutionControlClient:
    """HTTP client wrapper for execution-control remote execution APIs."""

    def __init__(
        self,
        *,
        device_id: str,
        resolve_base_url: BaseUrlResolver = resolve_execution_control_base_url,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._device_id = device_id
        self._resolve_base_url = resolve_base_url
        self._http_client = http_client

    def get_http_client(self) -> httpx.AsyncClient:
        """Lazy-init an httpx client pointed at the execution-control REST API."""
        if not self._http_client:
            control_plane_api_url = self._resolve_base_url()
            if not control_plane_api_url:
                raise ConnectionError(
                    "Execution control API URL not configured. "
                    "Set Runtime Environments config_url or "
                    "EXECUTION_CONTROL_API_URL / SITE_HUB_API_URL / CLOUD_API_URL."
                )
            api_key = os.getenv("CLOUD_API_KEY", "") or os.getenv(
                "CLOUD_PROVIDER_TOKEN", ""
            )
            headers = {
                "X-Device-Id": self._device_id,
            }
            if isinstance(api_key, str) and api_key.strip():
                headers["Authorization"] = f"Bearer {api_key.strip()}"
            self._http_client = httpx.AsyncClient(
                base_url=control_plane_api_url,
                headers=headers,
                timeout=30.0,
            )
        return self._http_client

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
        """Dispatch execution request to the execution control plane via HTTP."""
        client = self.get_http_client()
        governance = (
            request_payload.get("_governance", {})
            if isinstance(request_payload, dict)
            and isinstance(request_payload.get("_governance"), dict)
            else {}
        )
        resolved_site_key = site_key or governance.get("site_key") or os.getenv(
            "SITE_KEY"
        ) or tenant_id
        response = await client.post(
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
        """Probe control-plane runtime availability for a site/device request."""
        client = self.get_http_client()
        params: Dict[str, Any] = {"site_key": site_key}
        if isinstance(target_device_id, str) and target_device_id.strip():
            params["device_id"] = target_device_id.strip()

        response = await client.get(
            "/api/v1/executions/availability",
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
        """Fetch remote execution status from the execution control plane."""
        client = self.get_http_client()
        params = {"tenant_id": tenant_id} if tenant_id else None
        response = await client.get(f"/api/v1/executions/{execution_id}", params=params)
        response.raise_for_status()
        return response.json()

    async def get_remote_execution_result(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch remote execution terminal payload from the execution control plane."""
        client = self.get_http_client()
        params = {"tenant_id": tenant_id} if tenant_id else None
        response = await client.get(
            f"/api/v1/executions/{execution_id}/result",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    async def wait_for_terminal_result(
        self,
        execution_id: str,
        *,
        tenant_id: Optional[str] = None,
        timeout_seconds: float = 900.0,
        poll_interval_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        """Poll the execution control plane until a remote execution is terminal."""
        terminal_states = {"completed", "failed", "cancelled", "timeout"}
        started_at = datetime.now(timezone.utc)

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

            elapsed_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed_seconds >= max(1.0, float(timeout_seconds)):
                raise TimeoutError(
                    f"Timed out waiting for remote execution {execution_id} "
                    f"after {timeout_seconds:.1f}s"
                )

            await asyncio.sleep(max(0.1, float(poll_interval_seconds)))
