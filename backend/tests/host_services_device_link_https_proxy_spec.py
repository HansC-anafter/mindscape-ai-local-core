from __future__ import annotations

from backend.app.services.host_service_health_registry import HOST_SERVICE_HEALTH_URLS


def test_host_service_registry_includes_device_link_https_frontend_proxy() -> None:
    assert HOST_SERVICE_HEALTH_URLS["device-link-https"] == (
        "http://frontend:3000/api/v1/host/services/device-link-https/health"
    )
