from unittest.mock import patch

from backend.app.services.cloud_connector.connector import CloudConnector


def test_cloud_connector_prefers_device_id_env(monkeypatch):
    monkeypatch.setenv("DEVICE_ID", "gpu-node-01")

    with patch.object(
        CloudConnector,
        "_get_or_create_device_id",
        side_effect=AssertionError("should not auto-generate device id"),
    ):
        connector = CloudConnector(cloud_ws_url="ws://example.test/api/v1/executor/ws")

    assert connector.device_id == "gpu-node-01"


def test_cloud_connector_uses_explicit_device_id_over_env(monkeypatch):
    monkeypatch.setenv("DEVICE_ID", "gpu-node-01")

    with patch.object(
        CloudConnector,
        "_get_or_create_device_id",
        side_effect=AssertionError("should not auto-generate device id"),
    ):
        connector = CloudConnector(
            cloud_ws_url="ws://example.test/api/v1/executor/ws",
            device_id="override-node-02",
        )

    assert connector.device_id == "override-node-02"


def test_cloud_connector_falls_back_to_persisted_device_id(monkeypatch):
    monkeypatch.delenv("DEVICE_ID", raising=False)

    with patch.object(
        CloudConnector,
        "_get_or_create_device_id",
        return_value="persisted-node-03",
    ) as mocked_get:
        connector = CloudConnector(cloud_ws_url="ws://example.test/api/v1/executor/ws")

    assert connector.device_id == "persisted-node-03"
    mocked_get.assert_called_once_with()
