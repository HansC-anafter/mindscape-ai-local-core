from __future__ import annotations

from datetime import datetime, timezone
import json

import httpx
import pytest

from backend.app.services.device_node_host_runtime_client import (
    DeviceNodeHostRuntimeClient,
)
from backend.app.services.host_runtime_bindings.contracts import (
    DeviceHostBindingProjection,
)


NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
DIGEST = "a" * 64


def _binding() -> DeviceHostBindingProjection:
    return DeviceHostBindingProjection(
        binding_id="binding-a",
        device_id="device-a",
        capability_code="live_interface_interpreter",
        requirement_code="live_interface_automation",
        capability_version="0.1.36",
        runtime_digest=DIGEST,
        host_assets_digest=DIGEST,
        entrypoint="scripts/host_runtime_entry.py",
        entrypoint_digest="b" * 64,
        desired_state="materialized",
        generation=2,
        share_policy="workspace_grants",
        operations=["watch-screenshots"],
        permission_classes=["filesystem.read"],
        resource_lane="host.io.light",
        materialized_root="/runtime/lii",
    )


@pytest.mark.asyncio
async def test_device_node_attestation_client_uses_one_typed_tool_and_projection():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        projection = {
            "binding_id": "binding-a",
            "generation": 2,
            "runtime_digest": DIGEST,
            "executor_identity_digest": "c" * 64,
            "permission_revision": 7,
            "conditions": [
                {
                    "type": condition_type,
                    "status": "true",
                    "reason": "verified",
                    "observed_generation": 2,
                    "observed_at": NOW.isoformat(),
                }
                for condition_type in (
                    "Materialized",
                    "RuntimeDigestVerified",
                    "SupervisorReady",
                    "PermissionsReady",
                    "ResourceLaneReady",
                )
            ],
            "observed_at": NOW.isoformat(),
        }
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "host-runtime-attest",
                "result": {
                    "success": True,
                    "content": [
                        {"type": "text", "text": json.dumps(projection)}
                    ],
                },
            },
        )

    command = await DeviceNodeHostRuntimeClient(
        base_url="http://device-node",
        transport=httpx.MockTransport(handler),
    ).attest_binding(_binding())

    assert seen["params"]["name"] == "host_runtime_attest"
    assert seen["params"]["arguments"]["materialized_root"] == "/runtime/lii"
    assert command.generation == 2
    assert len(command.conditions) == 5
