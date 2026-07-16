"""Bounded original-path smoke gate for an activated pack candidate."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class OriginalPathSmokeReceipt:
    url: str
    status: int
    response_bytes: int

    def to_payload(self) -> dict[str, object]:
        return {
            "url": self.url,
            "status": self.status,
            "response_bytes": self.response_bytes,
        }


def verify_original_path_smoke() -> OriginalPathSmokeReceipt:
    """Require the existing 8300 user path before durable truth commit."""
    url = os.getenv(
        "MINDSCAPE_INSTALL_ORIGINAL_PATH_SMOKE_URL",
        "http://host.docker.internal:8300/healthz",
    ).strip()
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "mindscape-install-smoke/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=5.0) as response:
            body = response.read(8193)
            status = int(response.status)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("original_path_smoke_unavailable") from exc
    if status != 200:
        raise RuntimeError(f"original_path_smoke_status:{status}")
    if len(body) > 8192:
        raise RuntimeError("original_path_smoke_payload_oversize")
    return OriginalPathSmokeReceipt(
        url=url,
        status=status,
        response_bytes=len(body),
    )
