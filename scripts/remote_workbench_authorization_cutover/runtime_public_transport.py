"""Authenticated public HTTP/upgrade request helpers for runtime acceptance."""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from .http import HttpResponse
from .io import CutoverError


def assert_principal_response(
    response: HttpResponse,
    *,
    allowed: bool,
    expected_reason: str | None,
    upgrade: bool,
) -> None:
    """Require exact positive upstream or verified-principal denial semantics."""

    stage = response.headers.get("x-mindscape-remote-auth-stage")
    reason = response.headers.get("x-mindscape-remote-auth-reason")
    if allowed:
        expected = response.status == 101 if upgrade else 200 <= response.status < 300
        if not expected:
            raise CutoverError(
                "Authorized principal did not reach the expected upstream response"
            )
        return
    if response.status != 403 or stage != "principal_verified" or reason != expected_reason:
        raise CutoverError("Denied principal did not fail at the expected authorization stage")


def _headers(runtime: Any, assertion_path: Path, workspace_id: str, upgrade: bool) -> dict[str, str]:
    token = assertion_path.read_text(encoding="utf-8").strip()
    headers = {
        "Cookie": f"CF_Authorization={token}",
        "Referer": f"{runtime.public_origin}/workspaces/{workspace_id}",
    }
    if upgrade:
        headers.update(
            {
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Key": base64.b64encode(os.urandom(16)).decode("ascii"),
                "Sec-WebSocket-Version": "13",
            }
        )
    return headers


def principal_request(
    runtime: Any,
    assertion_path: Path,
    workspace_id: str,
    *,
    upgrade: bool,
    denied_capability: bool = False,
) -> HttpResponse:
    """Send one canonical positive or capability-negative public request."""

    if denied_capability:
        path = (
            "/api/v1/capability-packs/installed-capabilities/"
            f"mindscape_cloud_integration?workspace_id={workspace_id}"
        )
    else:
        path = (
            f"/api/v1/workspaces/{workspace_id}/device-bindings/control"
            if upgrade
            else f"/workspaces/{workspace_id}"
        )
    return runtime.http.request(
        "GET",
        f"{runtime.public_origin}{path}",
        headers=_headers(runtime, assertion_path, workspace_id, upgrade),
        timeout_seconds=10.0,
    )


def public_path_request(
    runtime: Any,
    assertion_path: Path,
    path: str,
    *,
    workspace_id: str,
    upgrade: bool = False,
) -> HttpResponse:
    """Send one bounded public-path request through the same cookie transport."""

    return runtime.http.request(
        "GET",
        f"{runtime.public_origin}{path}",
        headers=_headers(runtime, assertion_path, workspace_id, upgrade),
        timeout_seconds=10.0,
    )
