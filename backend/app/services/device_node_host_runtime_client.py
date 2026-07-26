"""Typed Local Core client for the single Device Node host-runtime facade."""

from __future__ import annotations

import os

import httpx
from pydantic import ValidationError

from backend.app.services.host_runtime_bindings.contracts import (
    AttestBindingCommand,
    DeviceHostBindingProjection,
)


class DeviceNodeHostRuntimeClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "DEVICE_NODE_URL",
                "http://host.docker.internal:3100",
            )
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def attest_binding(
        self,
        binding: DeviceHostBindingProjection,
    ) -> AttestBindingCommand:
        if binding.materialized_root is None:
            raise ValueError("host_runtime_binding_not_materialized")
        arguments = {
            "binding_id": binding.binding_id,
            "generation": binding.generation,
            "capability_code": binding.capability_code,
            "requirement_code": binding.requirement_code,
            "capability_version": binding.capability_version,
            "operations": binding.operations,
            "materialized_root": binding.materialized_root,
            "entrypoint": binding.entrypoint,
            "entrypoint_digest": binding.entrypoint_digest,
            "host_assets_digest": binding.host_assets_digest,
            "runtime_digest": binding.runtime_digest,
            "permission_classes": binding.permission_classes,
            "resource_lane": binding.resource_lane,
        }
        request = {
            "jsonrpc": "2.0",
            "id": "host-runtime-attest",
            "method": "tools/call",
            "params": {
                "name": "host_runtime_attest",
                "arguments": arguments,
            },
        }
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-Source": "host-runtime-binding-facade",
                },
            )
        if response.status_code != 200:
            raise ValueError("device_node_host_runtime_http_error")
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("error") is not None:
            raise ValueError("device_node_host_runtime_rpc_error")
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("success") is not True:
            raise ValueError("device_node_host_runtime_result_invalid")
        content = result.get("content")
        if (
            not isinstance(content, list)
            or len(content) != 1
            or not isinstance(content[0], dict)
            or set(content[0]) != {"type", "text"}
            or content[0].get("type") != "text"
            or not isinstance(content[0].get("text"), str)
        ):
            raise ValueError("device_node_host_runtime_content_invalid")
        try:
            return AttestBindingCommand.model_validate_json(content[0]["text"])
        except ValidationError as exc:
            raise ValueError("device_node_host_runtime_content_invalid") from exc
