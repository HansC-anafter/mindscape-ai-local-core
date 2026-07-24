from __future__ import annotations

import json
import queue
import stat

from scripts.e2e.live_media_device_source_client import (
    _DeviceControlReader,
    _control_ws_connect_options,
    _control_ws_url,
    _create_source_session,
    _heartbeat_ack_timeout_is_recoverable,
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


class _StreamingSocket:
    def __init__(self, events: list[object]) -> None:
        self.events = queue.Queue()
        for event in events:
            self.events.put(event)
        self.closed = False
        self.recv_calls = 0

    def recv(self) -> str:
        self.recv_calls += 1
        try:
            event = self.events.get(timeout=1.0)
        except queue.Empty:
            return ""
        if isinstance(event, Exception):
            raise event
        return str(event)

    def close(self) -> None:
        self.closed = True


def test_control_ws_url_preserves_origin_and_encodes_identity() -> None:
    assert _control_ws_url("https://core.test/", "ws one", "A B/C") == (
        "wss://core.test/api/v1/workspaces/ws%20one/"
        "device-bindings/A%20B%2FC/control"
    )


def test_control_socket_uses_application_heartbeat_as_single_liveness_owner() -> None:
    options = _control_ws_connect_options()

    assert options["open_timeout"] == 15
    assert options["close_timeout"] == 5
    assert options["ping_interval"] is None


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
    assert state["consecutive_heartbeat_timeouts"] == 0
    assert state["heartbeat_timeout_count"] == 0
    assert state["last_heartbeat_sequence"] == 0


def test_private_state_writer_is_atomic_and_owner_only(tmp_path) -> None:
    path = tmp_path / "source-state.json"

    _write_private_json(path, {"status": "active"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "active"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_control_reader_drains_snapshots_before_heartbeat_ack() -> None:
    socket = _StreamingSocket(
        [
            json.dumps({"type": "device_snapshot", "sequence": index})
            for index in range(32)
        ]
        + [json.dumps({"type": "heartbeat_ack"})]
    )
    reader = _DeviceControlReader(socket)
    reader.start()

    assert reader.wait_for("heartbeat_ack", timeout=2.0) == {
        "type": "heartbeat_ack"
    }
    assert socket.recv_calls >= 33

    reader.close()
    assert socket.closed is True


def test_control_reader_rejects_stale_heartbeat_ack_sequence() -> None:
    socket = _StreamingSocket(
        [
            json.dumps({"type": "heartbeat_ack", "heartbeat_sequence": 3}),
            json.dumps({"type": "heartbeat_ack", "heartbeat_sequence": 4}),
        ]
    )
    reader = _DeviceControlReader(socket)
    reader.start()

    assert reader.wait_for(
        "heartbeat_ack",
        timeout=2.0,
        heartbeat_sequence=4,
    ) == {"type": "heartbeat_ack", "heartbeat_sequence": 4}

    reader.close()


def test_control_reader_reports_closed_socket_without_json_decode_noise() -> None:
    socket = _StreamingSocket([""])
    reader = _DeviceControlReader(socket)
    reader.start()

    try:
        reader.wait_for("heartbeat_ack", timeout=2.0)
    except RuntimeError as exc:
        assert str(exc) == "device_source_socket_closed"
    else:
        raise AssertionError("closed control socket must fail")
    finally:
        reader.close()


def test_control_reader_treats_idle_read_timeout_as_non_terminal() -> None:
    socket = _StreamingSocket(
        [TimeoutError("Connection timed out"), json.dumps({"type": "heartbeat_ack"})]
    )
    reader = _DeviceControlReader(socket)
    reader.start()

    assert reader.wait_for("heartbeat_ack", timeout=2.0) == {
        "type": "heartbeat_ack"
    }
    assert socket.recv_calls >= 2

    reader.close()


def test_heartbeat_ack_timeout_budget_survives_transient_backend_delay() -> None:
    timeout = RuntimeError("device_source_event_timeout:heartbeat_ack")

    assert _heartbeat_ack_timeout_is_recoverable(
        timeout,
        consecutive_timeouts=3,
        miss_limit=4,
    ) is True
    assert _heartbeat_ack_timeout_is_recoverable(
        timeout,
        consecutive_timeouts=4,
        miss_limit=4,
    ) is False


def test_heartbeat_ack_timeout_budget_does_not_mask_reader_failure() -> None:
    failure = RuntimeError("device_source_socket_closed")

    try:
        _heartbeat_ack_timeout_is_recoverable(
            failure,
            consecutive_timeouts=1,
            miss_limit=4,
        )
    except RuntimeError as exc:
        assert exc is failure
    else:
        raise AssertionError("non-timeout source failures must remain terminal")
