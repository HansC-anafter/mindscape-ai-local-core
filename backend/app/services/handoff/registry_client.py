"""
HandoffRegistryClient — site-hub Handoff Registry API client (Contract 4).

Responsibilities (translate + verify + retry):
- Translate: Python dict <-> JSON API payloads
- Verify: spec_version check on responses
- Retry: exponential backoff + offline queue

Does NOT hold handoff state (state lives in site-hub Registry).
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)

# Offline queue directory
_QUEUE_DIR = Path(
    os.getenv(
        "HANDOFF_QUEUE_DIR",
        "/tmp/mindscape-handoff-queue",
    )
)


class RegistryUnavailable(Exception):
    """Raised when site-hub registry is not reachable after retries."""

    pass


class HandoffRegistryClient:
    """
    HTTP client for site-hub Handoff Registry API.

    Usage:
        client = HandoffRegistryClient()
        if not client.is_configured:
            return  # pure-local mode

        result = await client.create_handoff(...)
    """

    def __init__(
        self,
        registry_url: Optional[str] = None,
        device_id: Optional[str] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.registry_url = registry_url or os.getenv("HANDOFF_REGISTRY_URL")
        self.device_id = device_id or os.getenv("DEVICE_ID", "unknown")
        self.max_retries = max_retries
        self.base_delay = base_delay

    @property
    def is_configured(self) -> bool:
        """Return True if registry URL is set (not pure-local mode)."""
        return bool(self.registry_url)

    # --- State transition endpoints ---

    async def create_handoff(
        self,
        *,
        handoff_id: str,
        tenant_id: str,
        payload_type: str,
        payload: Dict[str, Any],
        target_device_id: Optional[str] = None,
        spec_version: str = "0.1",
    ) -> Dict[str, Any]:
        """POST /handoffs — create a new handoff."""
        return await self._post(
            "/handoffs",
            json={
                "id": handoff_id,
                "tenant_id": tenant_id,
                "spec_version": spec_version,
                "payload_type": payload_type,
                "payload": payload,
                "source_device_id": self.device_id,
                "target_device_id": target_device_id,
            },
        )

    async def claim_handoff(self, handoff_id: str) -> Dict[str, Any]:
        """POST /handoffs/{id}/claim — claim for processing."""
        return await self._post(
            f"/handoffs/{handoff_id}/claim",
            headers={"X-Device-ID": self.device_id},
        )

    async def commit_handoff(
        self,
        handoff_id: str,
        commitment: Dict[str, Any],
    ) -> Dict[str, Any]:
        """POST /handoffs/{id}/commit — submit commitment."""
        return await self._post(
            f"/handoffs/{handoff_id}/commit",
            json={
                "payload": commitment,
                "actor_device_id": self.device_id,
            },
        )

    async def complete_handoff(
        self,
        handoff_id: str,
        result_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /handoffs/{id}/complete — mark completed."""
        return await self._post(
            f"/handoffs/{handoff_id}/complete",
            json={
                "payload": result_payload or {},
                "actor_device_id": self.device_id,
            },
        )

    async def fail_handoff(
        self,
        handoff_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """POST /handoffs/{id}/fail — mark failed."""
        return await self._post(
            f"/handoffs/{handoff_id}/fail",
            json={
                "reason": reason,
                "actor_device_id": self.device_id,
            },
        )

    async def cancel_handoff(
        self,
        handoff_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """POST /handoffs/{id}/cancel — cancel handoff."""
        return await self._post(
            f"/handoffs/{handoff_id}/cancel",
            json={
                "reason": reason,
                "actor_device_id": self.device_id,
            },
        )

    # --- Query endpoints ---

    async def list_pending(
        self,
        state: str = "created",
    ) -> List[Dict[str, Any]]:
        """GET /handoffs?assigned_to={device_id}&state={state}."""
        data = await self._get(
            "/handoffs",
            params={
                "assigned_to": self.device_id,
                "state": state,
            },
        )
        return data.get("handoffs", [])

    async def get_timeline(self, handoff_id: str) -> Dict[str, Any]:
        """GET /handoffs/{id}/timeline — proof event chain."""
        return await self._get(f"/handoffs/{handoff_id}/timeline")

    # --- Event append ---

    async def append_event(
        self,
        handoff_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """POST /handoffs/{id}/events — append proof event."""
        event_id = str(uuid.uuid4())
        result = await self._post(
            f"/handoffs/{handoff_id}/events",
            json={
                "event_id": event_id,
                "event_type": event_type,
                "actor_device_id": self.device_id,
                "payload": payload or {},
            },
        )
        return result.get("event_id", event_id)

    # --- Internal HTTP helpers with retry ---

    async def _post(
        self,
        path: str,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        return await self._request("POST", path, json=json, headers=headers)

    async def _get(
        self,
        path: str,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Execute HTTP request with exponential backoff retry."""
        if not httpx:
            raise RegistryUnavailable("httpx not installed")
        if not self.registry_url:
            raise RegistryUnavailable("HANDOFF_REGISTRY_URL not configured")

        url = f"{self.registry_url.rstrip('/')}/api/v1/registry{path}"
        last_error = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method,
                        url,
                        json=json,
                        params=params,
                        headers=headers,
                    )
                    response.raise_for_status()
                    return response.json()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                delay = self.base_delay * (2**attempt)
                logger.warning(
                    "Registry request failed, retrying",
                    extra={"attempt": attempt + 1, "delay": delay, "error": str(e)},
                )
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as e:
                # Don't retry 4xx errors
                if 400 <= e.response.status_code < 500:
                    return e.response.json()
                last_error = e
                delay = self.base_delay * (2**attempt)
                await asyncio.sleep(delay)

        # All retries exhausted — queue offline if POST
        if method == "POST" and json:
            self._queue_offline(path, json)

        raise RegistryUnavailable(
            f"Registry unreachable after {self.max_retries} retries: {last_error}"
        )

    # --- Offline queue ---

    def _queue_offline(self, path: str, payload: Dict) -> None:
        """Save failed POST to local queue for later flush."""
        _QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "path": path,
            "payload": payload,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "device_id": self.device_id,
        }
        filename = f"{uuid.uuid4()}.json"
        queue_file = _QUEUE_DIR / filename
        queue_file.write_text(json.dumps(entry))
        logger.info("Queued offline handoff event", extra={"file": filename})

    async def flush_offline_queue(self) -> int:
        """Flush queued events to registry. Returns count of flushed items."""
        if not _QUEUE_DIR.exists():
            return 0

        flushed = 0
        for queue_file in sorted(_QUEUE_DIR.glob("*.json")):
            try:
                entry = json.loads(queue_file.read_text())
                await self._post(entry["path"], json=entry["payload"])
                queue_file.unlink()
                flushed += 1
            except RegistryUnavailable:
                # Still offline, stop trying
                break
            except Exception as e:
                logger.error("Failed to flush queued event", extra={"error": str(e)})

        if flushed:
            logger.info("Flushed offline queue", extra={"count": flushed})
        return flushed
