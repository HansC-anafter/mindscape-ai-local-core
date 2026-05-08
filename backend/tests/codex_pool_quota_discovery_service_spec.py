from types import SimpleNamespace

import pytest

from backend.app.services.codex_pool_health import HEALTH_METADATA_KEY
from backend.app.services.codex_pool_quota_discovery_service import (
    CodexPoolQuotaDiscoveryService,
)


def _runtime(runtime_id: str):
    return SimpleNamespace(
        id=runtime_id,
        auth_type="host_session",
        cooldown_until=None,
        last_error_code=None,
        extra_metadata={
            "CODEX_HOME": f"/tmp/accounts/acct-{runtime_id}",
            "HOME": f"/tmp/accounts/acct-{runtime_id}",
            "login_email": f"{runtime_id}@example.test",
            "account_key": runtime_id,
            "quota_scope_key": f"account:{runtime_id}",
            HEALTH_METADATA_KEY: {
                "seed_kind": "account_home",
                "health_state": "healthy",
            },
        },
    )


@pytest.mark.asyncio
async def test_quota_discovery_stamps_available_probe_state():
    runtime = _runtime("a")
    committed = []

    async def _probe(_input):
        return {"success": True, "returncode": 0, "output": '{"codex_pool_quota_probe":true}'}

    summary = await CodexPoolQuotaDiscoveryService(
        runtime_loader=lambda: [runtime],
        runtime_commit=lambda runtimes: committed.extend(runtimes),
        probe_runner=_probe,
    ).discover()

    assert summary.available_runtime_count == 1
    assert runtime.extra_metadata["probe_state"] == "available"
    assert runtime.extra_metadata["last_probe_success_at"]
    assert committed == [runtime]


@pytest.mark.asyncio
async def test_quota_discovery_stamps_auth_failure_probe_state():
    runtime = _runtime("a")

    async def _probe(_input):
        return {
            "success": False,
            "returncode": 1,
            "error": "Your access token could not be refreshed. Please log out and sign in again.",
        }

    summary = await CodexPoolQuotaDiscoveryService(
        runtime_loader=lambda: [runtime],
        runtime_commit=lambda _runtimes: None,
        probe_runner=_probe,
    ).discover()

    assert summary.failed_runtime_count == 1
    assert runtime.extra_metadata["probe_state"] == "auth_failed"
    assert runtime.last_error_code == "auth_failure"
