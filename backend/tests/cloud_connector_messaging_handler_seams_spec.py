import json
from datetime import datetime

import pytest

from backend.app.services.cloud_connector.messaging_handler import MessagingHandler


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_send_reply_preserves_messaging_reply_payload_shape():
    websocket = FakeWebSocket()
    handler = MessagingHandler(websocket=websocket, device_id="device_1")

    await handler._send_reply(
        "request_1",
        {
            "channel": "line",
            "user_id": "user_1",
            "reply_token": "reply_token_1",
            "channel_config_id": "channel_1",
        },
        {"status": "completed", "summary": "done"},
    )

    assert len(websocket.messages) == 1
    message = json.loads(websocket.messages[0])
    assert message["type"] == "messaging_reply"

    payload = message["payload"]
    assert payload["request_id"] == "request_1"
    assert payload["channel"] == "line"
    assert payload["user_id"] == "user_1"
    assert payload["reply_token"] == "reply_token_1"
    assert payload["channel_config_id"] == "channel_1"
    assert payload["device_id"] == "device_1"
    assert payload["result"] == {"status": "completed", "summary": "done"}
    assert datetime.fromisoformat(payload["timestamp"])
