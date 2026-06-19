from __future__ import annotations

import os


def build_host_service_health_urls() -> dict[str, str]:
    return {
        "stt": os.getenv("WHISPER_SERVICE_URL", "http://whisper-service:8006")
        + "/health",
        "xtts": os.getenv("XTTS_SERVICE_URL", "http://xtts-service:8020") + "/health",
        "mcp-gateway": os.getenv(
            "MCP_GATEWAY_HEALTH_URL", "http://host.docker.internal:8180/health"
        ),
        "mobile-workbench-gateway": os.getenv(
            "MOBILE_WORKBENCH_GATEWAY_HEALTH_URL",
            "http://frontend:3000/api/v1/host/services/mobile-workbench-gateway/health",
        ),
        "device-link-https": os.getenv(
            "DEVICE_LINK_HTTPS_HEALTH_URL",
            "http://frontend:3000/api/v1/host/services/device-link-https/health",
        ),
    }


HOST_SERVICE_HEALTH_URLS = build_host_service_health_urls()
