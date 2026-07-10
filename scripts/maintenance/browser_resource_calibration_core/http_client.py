"""Loopback API policy for calibration workload launch and reads."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


APPROVED_WORKLOADS = {
    "ig_analyze_following",
    "ig_batch_pin_references",
    "ig_pin_post_detail",
}
_READ_PATHS = {"/healthz", "/api/v1/host-resources/queue-utilization"}
_WRITE_PATH = "/api/v1/playbooks/execute/start"


@dataclass(frozen=True)
class HttpResult:
    status: int
    payload: dict[str, Any]
    elapsed_seconds: float


def validate_local_request(method: str, url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("calibration HTTP target must be local execution backend")
    if parsed.port != 8200:
        raise ValueError("calibration HTTP target must use execution port 8200")
    normalized_method = method.upper()
    if normalized_method == "GET" and parsed.path in _READ_PATHS:
        return
    if normalized_method != "POST" or parsed.path != _WRITE_PATH:
        raise ValueError("calibration HTTP mutation is forbidden")
    query = urllib.parse.parse_qs(parsed.query)
    workload = (query.get("playbook_code") or [""])[0]
    backend = (query.get("execution_backend") or [""])[0]
    if workload not in APPROVED_WORKLOADS or backend != "runner":
        raise ValueError("calibration may launch only approved runner playbooks")


class LocalApiClient:
    """Execute policy-checked loopback HTTP requests."""

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout_seconds: int = 5,
    ) -> HttpResult:
        import time

        validate_local_request(method, url)
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method.upper(),
        )
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError("local API response must be an object")
            return HttpResult(
                status=int(response.status),
                payload=decoded,
                elapsed_seconds=time.monotonic() - started,
            )
