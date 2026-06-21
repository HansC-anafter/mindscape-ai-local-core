"""HTTP and post-command recovery helpers for the PD real IG storyboard E2E."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from pd_real_ig_storyboard_e2e_core import _as_dict

_TRANSPORT_EXCEPTIONS = (
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
    http.client.BadStatusLine,
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
    socket.timeout,
    urllib.error.URLError,
)


def _http_json(method: str, url: str, payload: Any | None = None, timeout: int = 1200) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def _request_error_payload(
    exc: BaseException,
    *,
    method: str,
    url: str,
    meeting_id: str = "",
    command_id: str = "",
    context: str = "http_request",
) -> dict[str, Any]:
    reason = getattr(exc, "reason", None)
    return {
        "status": "transport_error",
        "context": context,
        "method": method,
        "url": url,
        "meeting_id": meeting_id,
        "command_id": command_id,
        "error_type": exc.__class__.__name__,
        "error": str(reason or exc),
        "resumable_after_transport_error": True,
    }


def _submit_command_with_recovery_marker(
    *,
    args: argparse.Namespace,
    submit_url: str,
    envelope: dict[str, Any],
    meeting_id: str,
    command_id: str,
    http_json: Callable[..., Any] = _http_json,
) -> tuple[dict[str, Any], bool]:
    try:
        response = http_json(
            "POST",
            submit_url,
            envelope,
            timeout=args.command_timeout_seconds + 60,
        )
        return _as_dict(response), False
    except _TRANSPORT_EXCEPTIONS as exc:
        return (
            _request_error_payload(
                exc,
                method="POST",
                url=submit_url,
                meeting_id=meeting_id,
                command_id=command_id,
                context="command_submit",
            ),
            True,
        )


def _session_is_terminal(session_response: Any) -> bool:
    session = _as_dict(session_response)
    status = str(session.get("status") or "").strip().lower()
    return bool(session.get("ended_at")) or status in {
        "closed",
        "completed",
        "complete",
        "failed",
        "cancelled",
        "canceled",
        "ended",
    }


def _safe_fetch_json(
    *,
    method: str,
    url: str,
    timeout: int,
    meeting_id: str,
    command_id: str,
    context: str,
    http_json: Callable[..., Any] = _http_json,
) -> dict[str, Any]:
    try:
        return _as_dict(http_json(method, url, timeout=timeout))
    except _TRANSPORT_EXCEPTIONS as exc:
        return _request_error_payload(
            exc,
            method=method,
            url=url,
            meeting_id=meeting_id,
            command_id=command_id,
            context=context,
        )


def _fetch_session_and_events(
    *,
    args: argparse.Namespace,
    session_url: str,
    events_url: str,
    meeting_id: str,
    command_id: str,
    poll_until_terminal: bool,
    http_json: Callable[..., Any] = _http_json,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + max(0, int(args.post_command_poll_seconds))
    interval = max(0.0, float(args.post_command_poll_interval_seconds))
    attempts = 0
    session_response: dict[str, Any] = {}
    events_response: dict[str, Any] = {}
    terminal = False

    while True:
        attempts += 1
        session_response = _safe_fetch_json(
            method="GET",
            url=session_url,
            timeout=args.http_timeout_seconds,
            meeting_id=meeting_id,
            command_id=command_id,
            context="meeting_session_fetch",
            http_json=http_json,
        )
        events_response = _safe_fetch_json(
            method="GET",
            url=events_url,
            timeout=args.http_timeout_seconds,
            meeting_id=meeting_id,
            command_id=command_id,
            context="meeting_events_fetch",
            http_json=http_json,
        )
        terminal = _session_is_terminal(session_response)
        if terminal or not poll_until_terminal or time.monotonic() >= deadline:
            break
        if interval:
            time.sleep(interval)

    recovery = {
        "poll_until_terminal": poll_until_terminal,
        "poll_attempts": attempts,
        "session_terminal": terminal,
        "session_status": session_response.get("status"),
        "session_ended_at": session_response.get("ended_at"),
    }
    return session_response, events_response, recovery
