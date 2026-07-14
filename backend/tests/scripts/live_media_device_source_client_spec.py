from __future__ import annotations

import json
import stat

from scripts.e2e.live_media_device_source_client import (
    _control_ws_url,
    _create_source_session,
    _write_private_json,
)


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {"pairing_code": "A B/C"}


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self) -> str:
        return json.dumps({"type": "session_paired", "session_id": "device-one"})

    def close(self) -> None:
        self.closed = True


def test_control_ws_url_preserves_origin_and_encodes_identity() -> None:
    assert _control_ws_url("https://core.test/", "ws one", "A B/C") == (
        "wss://core.test/api/v1/workspaces/ws%20one/"
        "device-bindings/A%20B%2FC/control"
    )


def test_create_source_session_uses_product_pairing_and_control_paths() -> None:
    calls: list[dict] = []
    socket = _Socket()

    created_socket, state = _create_source_session(
        api_base="http://127.0.0.1:8200",
        workspace_id="workspace-one",
        device_id="device-source",
        display_name="Device source",
        request_post=lambda url, **kwargs: calls.append(
            {"url": url, **kwargs}
        )
        or _Response(),
        connect=lambda url, **kwargs: calls.append(
            {"socket_url": url, **kwargs}
        )
        or socket,
    )

    assert created_socket is socket
    assert calls[0]["url"].endswith(
        "/workspaces/workspace-one/device-bindings/pairing-codes"
    )
    assert calls[1]["socket_url"].endswith(
        "/workspaces/workspace-one/device-bindings/A%20B%2FC/control"
    )
    assert socket.sent[0]["type"] == "source_join"
    assert socket.sent[0]["metadata"] == {"e2e": True, "transport": "whip"}
    assert state["device_session_id"] == "device-one"
    assert state["status"] == "active"


def test_private_state_writer_is_atomic_and_owner_only(tmp_path) -> None:
    path = tmp_path / "source-state.json"

    _write_private_json(path, {"status": "active"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "active"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
