#!/usr/bin/env python3
"""Maintain one formal device-binding source session for live-media E2E runs."""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

import requests


def _control_ws_url(api_base: str, workspace_id: str, pairing_code: str) -> str:
    parsed = urlsplit(api_base.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = (
        f"/api/v1/workspaces/{quote(workspace_id, safe='')}"
        f"/device-bindings/{quote(pairing_code, safe='')}/control"
    )
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(path)
    path.chmod(0o600)


def _receive_event(socket: Any, expected_type: str) -> dict[str, Any]:
    for _ in range(16):
        event = json.loads(socket.recv())
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error":
            raise RuntimeError(str(event.get("reason") or "device_source_error"))
        if event.get("type") == expected_type:
            return event
    raise RuntimeError(f"device_source_event_missing:{expected_type}")


class _DeviceControlReader:
    """Continuously drain control frames so websocket keepalives remain serviced."""

    _FORWARDED_TYPES = frozenset(
        {"error", "heartbeat_ack", "session_closed"}
    )

    def __init__(self, socket: Any) -> None:
        self._socket = socket
        self._events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="live-media-device-control-reader",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def wait_for(self, expected_type: str, *, timeout: float = 15.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"device_source_event_timeout:{expected_type}")
            try:
                event = self._events.get(timeout=remaining)
            except queue.Empty as exc:
                raise RuntimeError(
                    f"device_source_event_timeout:{expected_type}"
                ) from exc
            event_type = str(event.get("type") or "")
            if event_type in {"error", "reader_failed"}:
                raise RuntimeError(str(event.get("reason") or "device_source_error"))
            if event_type == expected_type:
                return event

    def close(self) -> None:
        self._stop.set()
        self._socket.close()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _publish(self, event: dict[str, Any]) -> None:
        try:
            self._events.put_nowait(event)
            return
        except queue.Full:
            pass
        try:
            self._events.get_nowait()
        except queue.Empty:
            pass
        self._events.put_nowait(event)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                raw = self._socket.recv()
                if not raw:
                    raise RuntimeError("device_source_socket_closed")
                event = json.loads(raw)
                if not isinstance(event, dict):
                    continue
                if event.get("type") in self._FORWARDED_TYPES:
                    self._publish(event)
            except Exception as exc:
                if not self._stop.is_set():
                    self._publish(
                        {"type": "reader_failed", "reason": str(exc)[:160]}
                    )
                return


def _create_source_session(
    *,
    api_base: str,
    workspace_id: str,
    device_id: str,
    display_name: str,
    request_post: Callable[..., Any] = requests.post,
    connect: Callable[..., Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    if connect is None:
        from websocket import create_connection

        connect = create_connection
    response = request_post(
        f"{api_base.rstrip('/')}/api/v1/workspaces/"
        f"{quote(workspace_id, safe='')}/device-bindings/pairing-codes",
        json={"expires_in_seconds": 300},
        timeout=10,
    )
    response.raise_for_status()
    pairing = response.json()
    pairing_code = str(pairing.get("pairing_code") or "").strip()
    if not pairing_code:
        raise RuntimeError("device_pairing_code_missing")
    socket = connect(
        _control_ws_url(api_base, workspace_id, pairing_code),
        timeout=15,
        enable_multithread=True,
    )
    socket.send(
        json.dumps(
            {
                "type": "source_join",
                "device_id": device_id,
                "display_name": display_name,
                "source_types": ["phone_camera"],
                "metadata": {"e2e": True, "transport": "whip"},
            },
            separators=(",", ":"),
        )
    )
    paired = _receive_event(socket, "session_paired")
    session_id = str(paired.get("session_id") or "").strip()
    if not session_id:
        socket.close()
        raise RuntimeError("device_session_id_missing")
    return socket, {
        "schema_version": "live_media_device_source_e2e.v1",
        "status": "active",
        "workspace_id": workspace_id,
        "pairing_code": pairing_code,
        "device_session_id": session_id,
        "device_id": device_id,
        "connected_at_epoch": time.time(),
        "last_heartbeat_at_epoch": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8200")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--state-path", type=Path, required=True)
    parser.add_argument("--device-id", default="formal-whip-e2e-source")
    parser.add_argument("--display-name", default="Formal WHIP E2E source")
    parser.add_argument("--heartbeat-seconds", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stop_requested = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    socket = None
    reader = None
    state: dict[str, Any] = {
        "schema_version": "live_media_device_source_e2e.v1",
        "status": "starting",
        "workspace_id": args.workspace_id,
    }
    _write_private_json(args.state_path, state)
    try:
        socket, state = _create_source_session(
            api_base=args.api_base,
            workspace_id=args.workspace_id,
            device_id=args.device_id,
            display_name=args.display_name,
        )
        _write_private_json(args.state_path, state)
        reader = _DeviceControlReader(socket)
        reader.start()
        next_heartbeat = time.monotonic()
        while not stop_requested:
            now = time.monotonic()
            if now < next_heartbeat:
                time.sleep(min(0.25, next_heartbeat - now))
                continue
            socket.send('{"type":"heartbeat"}')
            reader.wait_for("heartbeat_ack")
            state["last_heartbeat_at_epoch"] = time.time()
            _write_private_json(args.state_path, state)
            next_heartbeat = now + max(1.0, args.heartbeat_seconds)
        socket.send('{"type":"session_close"}')
        reader.wait_for("session_closed")
        state["status"] = "closed"
        state["closed_at_epoch"] = time.time()
        _write_private_json(args.state_path, state)
        return 0
    except Exception as exc:
        state["status"] = "failed"
        state["reason"] = str(exc)[:160]
        state["failed_at_epoch"] = time.time()
        _write_private_json(args.state_path, state)
        return 1
    finally:
        if reader is not None:
            reader.close()
        elif socket is not None:
            socket.close()


if __name__ == "__main__":
    raise SystemExit(main())
