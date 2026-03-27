"""
Compatibility wrapper for the historical Gemini import path.

The shared host bridge WebSocket client now lives under external_agents.bridge.
"""

from backend.app.services.external_agents.bridge.host_ws_client import (
    HostBridgeWSClient,
    main,
)

GeminiCLIWSClient = HostBridgeWSClient

__all__ = [
    "GeminiCLIWSClient",
    "HostBridgeWSClient",
    "main",
]


if __name__ == "__main__":
    main()
