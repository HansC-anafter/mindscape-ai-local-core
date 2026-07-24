from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import websocket

from .events import emit


class GuidanceSocket:
    def __init__(
        self,
        *,
        api_base: str,
        workspace_id: str,
        meeting_id: str,
        practice_session_id: str,
        live_session_id: str,
    ) -> None:
        base = api_base.replace("https://", "wss://").replace(
            "http://", "ws://"
        ).rstrip("/")
        self.url = (
            f"{base}/api/v1/workspaces/{quote(workspace_id, safe='')}"
            f"/meetings/{quote(meeting_id, safe='')}"
            f"/motion-guidance/{quote(practice_session_id, safe='')}/stream"
        )
        self.socket = websocket.create_connection(self.url, timeout=5)
        self.socket.settimeout(0.2)
        self.send(
            {
                "type": "session_start",
                "event_id": f"{practice_session_id}:session_start",
                "live_session_id": live_session_id,
            }
        )

    def send(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        self.socket.send(json.dumps(message))
        return self.read_events()

    def read_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            try:
                raw = self.socket.recv()
                if not raw:
                    break
                events.append(json.loads(raw))
            except TimeoutError:
                break
            except websocket.WebSocketTimeoutException:
                break
            except websocket.WebSocketConnectionClosedException:
                break
            except json.JSONDecodeError:
                break
        return events

    def close(self) -> None:
        try:
            try:
                self.send(
                    {
                        "type": "session_close",
                        "event_id": "rtmp_publisher:close",
                    }
                )
            except Exception as exc:
                emit({"event": "guidance_socket_close_failed", "error": str(exc)})
        finally:
            self.socket.close()


__all__ = ["GuidanceSocket"]
