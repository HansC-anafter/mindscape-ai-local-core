"""Bounded probes for Remote Workbench bridge liveness."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BRIDGE_USER_AGENT = "mindscape-bridge-monitor/1"
CONNECTOR_RESPONSE_LIMIT_BYTES = 16_384
DOCKER_RESPONSE_LIMIT_BYTES = 262_144
CLOUDFLARED_CONTAINER_ENVIRONMENT = [
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt",
]
CLOUDFLARED_CONTAINER_USER = "65532:65532"
CLOUDFLARED_ENTRYPOINT = ["cloudflared", "--no-autoupdate"]
CLOUDFLARED_COMMAND = [
    "tunnel",
    "--no-autoupdate",
    "--metrics",
    "0.0.0.0:2000",
    "run",
    "--token-file",
    "/etc/cloudflared/tunnel-token",
]


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


def _decode_chunked_body(body: bytes, limit_bytes: int = 65_536) -> bytes:
    decoded: list[bytes] = []
    remaining = body
    decoded_bytes = 0
    while remaining and decoded_bytes <= limit_bytes:
        size_line, separator, remaining = remaining.partition(b"\r\n")
        if not separator:
            return body
        try:
            size = int(size_line.split(b";", 1)[0], 16)
        except ValueError:
            return body
        if size == 0:
            return b"".join(decoded)
        if size > limit_bytes - decoded_bytes or len(remaining) < size + 2:
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
    ready_connections: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        payload = asdict(self)
        if self.ready_connections is None:
            payload.pop("ready_connections")
        return payload


class BridgeProbes:
    """Probe Docker, the local origin, connector, and public edge."""

    def __init__(
        self,
        *,
        docker_socket_path: Path,
        container_name: str,
        network_name: str,
        token_path: Path,
        cloudflared_image: str,
        metrics_host_port: int,
        local_origin_url: str,
        connector_ready_url: str,
        public_origin_url: str,
        probe_timeout_seconds: float,
        public_timeout_seconds: float,
        connector_minimum_ready_connections: int = 2,
    ) -> None:
        self.docker_socket_path = docker_socket_path
        self.container_name = container_name
        self.network_name = network_name
        self.token_path = token_path
        self.cloudflared_image = cloudflared_image
        self.metrics_host_port = metrics_host_port
        self.local_origin_url = local_origin_url
        self.connector_ready_url = connector_ready_url
        self.public_origin_url = public_origin_url
        self.probe_timeout_seconds = probe_timeout_seconds
        self.public_timeout_seconds = public_timeout_seconds
        self.connector_minimum_ready_connections = connector_minimum_ready_connections
        self._container_observation: (
            tuple[ProbeResult, dict[str, Any] | None] | None
        ) = None

    def _observe_container(self) -> tuple[ProbeResult, dict[str, Any] | None]:
        name = urllib.parse.quote(self.container_name, safe="")
        request = (
            f"GET /containers/{name}/json HTTP/1.1\r\n"
            "Host: docker\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        chunks: list[bytes] = []
        total = 0
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(self.probe_timeout_seconds)
                client.connect(str(self.docker_socket_path))
                client.sendall(request)
                while total <= DOCKER_RESPONSE_LIMIT_BYTES:
                    chunk = client.recv(
                        min(16_384, DOCKER_RESPONSE_LIMIT_BYTES + 1 - total)
                    )
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
        except (OSError, TimeoutError):
            return ProbeResult(False, "docker_unavailable"), None
        if total > DOCKER_RESPONSE_LIMIT_BYTES:
            return ProbeResult(False, "docker_response_oversized"), None
        header, separator, body = b"".join(chunks).partition(b"\r\n\r\n")
        if not separator:
            return ProbeResult(False, "docker_response_malformed"), None
        try:
            status = int(header.split(b" ", 2)[1])
        except (IndexError, ValueError):
            return ProbeResult(False, "docker_response_malformed"), None
        if status == 404:
            return ProbeResult(False, "tunnel_not_running"), None
        if status != 200:
            return ProbeResult(False, "docker_unavailable", str(status)), None
        if b"transfer-encoding: chunked" in header.lower():
            body = _decode_chunked_body(body, DOCKER_RESPONSE_LIMIT_BYTES)
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError, RecursionError):
            return ProbeResult(False, "docker_response_malformed"), None
        if not isinstance(payload, dict):
            return ProbeResult(False, "docker_response_malformed"), None
        return ProbeResult(True, "ok"), payload

    def _container_contract_valid(self, payload: dict[str, Any]) -> bool:
        state = payload.get("State")
        config = payload.get("Config")
        host_config = payload.get("HostConfig")
        mounts = payload.get("Mounts")
        if not all(
            isinstance(value, dict) for value in (state, config, host_config)
        ) or not isinstance(mounts, list):
            return False
        restart_policy = host_config.get("RestartPolicy")
        if not isinstance(restart_policy, dict):
            return False
        expected_bindings = {
            "2000/tcp": [
                {
                    "HostIp": "127.0.0.1",
                    "HostPort": str(self.metrics_host_port),
                }
            ]
        }
        image_id = payload.get("Image")
        image_digest = (
            image_id.removeprefix("sha256:")
            if isinstance(image_id, str)
            else ""
        )
        if len(image_digest) != 64 or any(
            character not in "0123456789abcdef" for character in image_digest
        ):
            return False
        if len(mounts) != 1 or not isinstance(mounts[0], dict):
            return False
        mount = mounts[0]
        return (
            payload.get("Name") == f"/{self.container_name}"
            and state.get("Running") is True
            and restart_policy.get("Name") == "unless-stopped"
            and host_config.get("NetworkMode") == self.network_name
            and host_config.get("PortBindings") == expected_bindings
            and host_config.get("Privileged") is False
            and mount.get("Type") == "bind"
            and mount.get("Source") == str(self.token_path)
            and mount.get("Destination") == "/etc/cloudflared/tunnel-token"
            and mount.get("RW") is False
            and config.get("Image") == self.cloudflared_image
            and config.get("Env") == CLOUDFLARED_CONTAINER_ENVIRONMENT
            and config.get("User") == CLOUDFLARED_CONTAINER_USER
            and config.get("Entrypoint") == CLOUDFLARED_ENTRYPOINT
            and config.get("Cmd") == CLOUDFLARED_COMMAND
        )

    def docker(self) -> ProbeResult:
        """Observe Docker and cache the same container read for tunnel()."""

        self._container_observation = self._observe_container()
        result, _payload = self._container_observation
        if not result.ok and result.code != "tunnel_not_running":
            return result
        return ProbeResult(True, "ok")

    def tunnel(self) -> ProbeResult:
        """Validate the cached bounded Docker container observation in process."""

        observation = self._container_observation or self._observe_container()
        self._container_observation = None
        result, payload = observation
        if not result.ok:
            return result
        if payload is None or not self._container_contract_valid(payload):
            return ProbeResult(False, "tunnel_contract_mismatch")
        return ProbeResult(True, "ok")

    def _http_response(
        self,
        url: str,
        *,
        timeout: float,
        allow_redirect: bool,
        body_limit_bytes: int = 0,
    ) -> tuple[ProbeResult, bytes]:
        handlers: list[Any] = [urllib.request.ProxyHandler({})]
        if not allow_redirect:
            handlers.append(_NoRedirect())
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(
            url,
            method="GET",
            headers={"User-Agent": BRIDGE_USER_AGENT},
        )
        body = b""
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(response.status)
                if body_limit_bytes:
                    body = response.read(body_limit_bytes + 1)
        except urllib.error.HTTPError as error:
            status = int(error.code)
        except (urllib.error.URLError, TimeoutError, OSError):
            return ProbeResult(False, "http_unreachable"), b""
        if body_limit_bytes and len(body) > body_limit_bytes:
            return ProbeResult(False, "http_response_oversized", str(status)), b""
        if 200 <= status < 400:
            return ProbeResult(True, "ok", str(status)), body
        return ProbeResult(False, "http_status", str(status)), body

    def _http(self, url: str, *, timeout: float, allow_redirect: bool) -> ProbeResult:
        result, _body = self._http_response(
            url,
            timeout=timeout,
            allow_redirect=allow_redirect,
        )
        return result

    def local_origin(self) -> ProbeResult:
        """Check dependency-light local frontend liveness."""

        return self._http(
            self.local_origin_url,
            timeout=self.probe_timeout_seconds,
            allow_redirect=False,
        )

    def connector(self) -> ProbeResult:
        """Check the cloudflared connector readiness endpoint."""

        result, body = self._http_response(
            self.connector_ready_url,
            timeout=self.probe_timeout_seconds,
            allow_redirect=False,
            body_limit_bytes=CONNECTOR_RESPONSE_LIMIT_BYTES,
        )
        if not result.ok:
            return result
        if not body.strip():
            return ProbeResult(
                False, "connector_readiness_malformed", result.detail
            )
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, ValueError, RecursionError):
            return ProbeResult(
                False, "connector_readiness_malformed", result.detail
            )
        ready_connections = (
            payload.get("readyConnections") if isinstance(payload, dict) else None
        )
        if (
            not isinstance(ready_connections, int)
            or isinstance(ready_connections, bool)
            or ready_connections < 0
        ):
            return ProbeResult(
                False, "connector_readiness_malformed", result.detail
            )
        if ready_connections < self.connector_minimum_ready_connections:
            return ProbeResult(
                False,
                "connector_capacity",
                result.detail,
                ready_connections,
            )
        return ProbeResult(
            True,
            result.code,
            result.detail,
            ready_connections,
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
