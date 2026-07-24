from __future__ import annotations

import json

from scripts.e2e.live_media_receiver_status_monitor import (
    build_request,
    compact_status,
    read_receiver_status,
)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        payload = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "active",
                                "state": "analyzing",
                                "metrics": {
                                    "accepted_windows": 12,
                                    "failed_windows": 0,
                                },
                            }
                        ),
                    }
                ]
            }
        }
        return json.dumps(payload).encode("utf-8")


def test_build_request_targets_exact_receiver_identity() -> None:
    request = build_request("media-one")

    assert request["params"]["name"] == "capture_relay_control"
    assert request["params"]["arguments"] == {
        "action": "receiver_status",
        "media_session_id": "media-one",
    }


def test_read_and_compact_receiver_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _Response(),
    )

    status = read_receiver_status(
        mcp_url="http://core.test/mcp",
        request_payload=build_request("media-one"),
        timeout_seconds=1,
    )
    compact = compact_status({"observed_at": "now", **status})

    assert compact["status"] == "active"
    assert compact["state"] == "analyzing"
    assert compact["accepted"] == 12
    assert compact["failed"] == 0
