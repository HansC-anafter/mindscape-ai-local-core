"""Bounded probes for Remote Workbench bridge liveness."""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _decode_chunked_body(body: bytes) -> bytes:
    decoded: list[bytes] = []
    remaining = body
    decoded_bytes = 0
    while remaining and decoded_bytes <= 65_536:
        size_line, separator, remaining = remaining.partition(b"\r\n")
        if not separator:
            return body
        try:
            size = int(size_line.split(b";", 1)[0], 16)
        except ValueError:
            return body
        if size == 0:
            return b"".join(decoded)
        if size > 65_536 - decoded_bytes or len(remaining) < size + 2:
            return body
        decoded.append(remaining[:size])
        decoded_bytes += size
        remaining = remaining[size + 2 :]
    return body


@dataclass(frozen=True)
class ProbeResult:
    """Sanitized result from one bounded liveness probe."""

    ok: bool
    code: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return asdict(self)


class BridgeProbes:
    """Probe Docker, the local origin, connector, and public edge."""

    def __init__(
        self,
        *,
        launcher_path: Path,
        docker_socket_path: Path,
        local_origin_url: str,
        connector_ready_url: str,
        public_origin_url: str,
        probe_timeout_seconds: float,
        public_timeout_seconds: float,
    ) -> None:
        self.launcher_path = launcher_path
        self.docker_socket_path = docker_socket_path
        self.local_origin_url = local_origin_url
        self.connector_ready_url = connector_ready_url
        self.public_origin_url = public_origin_url
        self.probe_timeout_seconds = probe_timeout_seconds
        self.public_timeout_seconds = public_timeout_seconds

    def docker(self) -> ProbeResult:
        """Check whether the Docker API is available."""

        request = b"GET /_ping HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n"
        chunks: list[bytes] = []
        total = 0
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.probe_timeout_seconds)
                client.connect(str(self.docker_socket_path))
                client.sendall(request)
                while total < 65_536:
                    chunk = client.recv(min(16_384, 65_536 - total))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
        except (OSError, TimeoutError):
            return ProbeResult(False, "docker_unavailable")
        header, separator, body = b"".join(chunks).partition(b"\r\n\r\n")
        if not separator:
            return ProbeResult(False, "docker_response_malformed")
        try:
            status = int(header.split(b" ", 2)[1])
        except (IndexError, ValueError):
            return ProbeResult(False, "docker_response_malformed")
        if b"transfer-encoding: chunked" in header.lower():
            body = _decode_chunked_body(body)
        if status != 200 or body.strip() != b"OK":
            return ProbeResult(False, "docker_unavailable")
        return ProbeResult(True, "ok")

    def tunnel(self) -> ProbeResult:
        """Read the canonical launcher's sanitized tunnel status."""

        try:
            result = subprocess.run(
                [str(self.launcher_path), "status", "--json"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.probe_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ProbeResult(False, "launcher_unavailable")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return ProbeResult(False, "launcher_status_malformed")
        if result.returncode != 0 or payload.get("running") is not True:
            return ProbeResult(False, "tunnel_not_running")
        if payload.get("contract_conformant") is not True:
            return ProbeResult(False, "tunnel_contract_mismatch")
        return ProbeResult(True, "ok")

    def _http(self, url: str, *, timeout: float, allow_redirect: bool) -> ProbeResult:
        handlers: list[Any] = [urllib.request.ProxyHandler({})]
        if not allow_redirect:
            handlers.append(_NoRedirect())
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(url, method="GET")
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(response.status)
        except urllib.error.HTTPError as error:
            status = int(error.code)
        except (urllib.error.URLError, TimeoutError, OSError):
            return ProbeResult(False, "http_unreachable")
        if 200 <= status < 400:
            return ProbeResult(True, "ok", str(status))
        return ProbeResult(False, "http_status", str(status))

    def local_origin(self) -> ProbeResult:
        """Check dependency-light local frontend liveness."""

        return self._http(
            self.local_origin_url,
            timeout=self.probe_timeout_seconds,
            allow_redirect=False,
        )

    def connector(self) -> ProbeResult:
        """Check the cloudflared connector readiness endpoint."""

        return self._http(
            self.connector_ready_url,
            timeout=self.probe_timeout_seconds,
            allow_redirect=False,
        )

    def public_origin(self) -> ProbeResult:
        """Require the exact Cloudflare Access redirect from the public edge."""

        result = self._http(
            self.public_origin_url,
            timeout=self.public_timeout_seconds,
            allow_redirect=False,
        )
        if result.ok and result.detail == "302":
            return result
        if result.ok:
            return ProbeResult(False, "access_redirect_missing", result.detail)
        return result
