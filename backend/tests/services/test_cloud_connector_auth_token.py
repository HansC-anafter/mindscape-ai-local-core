import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))
sys.path.insert(0, str(_HERE.parents[3]))

try:
    from backend.app.services.cloud_connector.connector import CloudConnector
except ModuleNotFoundError:
    from app.services.cloud_connector.connector import CloudConnector


@pytest.mark.asyncio
async def test_cloud_connector_prefers_explicit_device_token_for_ws_auth(monkeypatch):
    monkeypatch.setenv("DEVICE_ID", "test-device-01")
    monkeypatch.setenv("EXECUTION_CONTROL_DEVICE_TOKEN", "device:token:value")

    connector = CloudConnector(cloud_ws_url="ws://example.test/api/v1/executor/ws")

    token = await connector.get_device_token()

    assert token == "device:token:value"


@pytest.mark.asyncio
async def test_cloud_connector_falls_back_to_google_runtime_token_for_site_hub_ws(monkeypatch):
    monkeypatch.setenv("DEVICE_ID", "test-device-01")
    for name in (
        "EXECUTION_CONTROL_DEVICE_TOKEN",
        "CLOUD_DEVICE_TOKEN",
        "SITE_HUB_DEVICE_TOKEN",
        "EXECUTION_CONTROL_USER_TOKEN",
        "CLOUD_EXECUTION_USER_TOKEN",
        "SITE_HUB_USER_TOKEN",
        "CLOUD_PROVIDER_TOKEN",
        "CLOUD_API_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    connector = CloudConnector(cloud_ws_url="ws://example.test/api/v1/executor/ws")

    async def _fake_runtime_token():
        return "ya29.test-runtime-token"

    connector._get_runtime_oauth_token = _fake_runtime_token

    token = await connector.get_device_token()

    assert token == "ya29.test-runtime-token"


@pytest.mark.asyncio
async def test_cloud_connector_prefers_fresh_gce_metadata_token_for_site_hub_ws(monkeypatch):
    monkeypatch.setenv("DEVICE_ID", "test-device-01")
    monkeypatch.setenv("CLOUD_PROVIDER_TOKEN", "ya29.stale-env-token")

    connector = CloudConnector(cloud_ws_url="ws://example.test/api/v1/executor/ws")

    async def _fake_metadata_token():
        return "ya29.test-metadata-token"

    async def _fake_runtime_token():
        return "ya29.test-runtime-token"

    connector._get_gce_metadata_google_access_token = _fake_metadata_token
    connector._get_runtime_oauth_token = _fake_runtime_token

    token = await connector.get_device_token()

    assert token == "ya29.test-metadata-token"
