"""Bounded public HTTP materialization seam for linked Browser Capture sources."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit


class PublicHttpMaterializationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PublicHttpMaterialization:
    url: str
    final_url: str
    content_type: str
    body: bytes
    status_code: int


MAX_BODY_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/markdown",
    "text/plain",
    "application/pdf",
}


def _assert_public_host(host: str) -> None:
    lowered = host.strip(".").lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        raise PublicHttpMaterializationError("private_host", "Private hosts are not allowed.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(lowered, None)}
    except OSError as exc:
        raise PublicHttpMaterializationError("dns_failed", "Public host DNS resolution failed.") from exc
    for address in addresses:
        parsed = ipaddress.ip_address(address)
        if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved:
            raise PublicHttpMaterializationError("private_address", "Private or reserved addresses are not allowed.")


def validate_public_url(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicHttpMaterializationError("invalid_url", "Only absolute HTTP(S) URLs are accepted.")
    _assert_public_host(parsed.hostname)
    return parsed.geturl()


async def materialize_public_http(
    url: str,
    *,
    client: Any,
    max_body_bytes: int = MAX_BODY_BYTES,
    max_redirects: int = MAX_REDIRECTS,
) -> PublicHttpMaterialization:
    """Fetch a public linked source with bounded redirects, bytes, and type."""

    current = validate_public_url(url)
    for redirect_count in range(max_redirects + 1):
        parsed = urlsplit(current)
        response = await client.get(
            current,
            follow_redirects=False,
            timeout=10.0,
            headers={"Accept": ", ".join(sorted(ALLOWED_CONTENT_TYPES))},
        )
        if 300 <= response.status_code < 400:
            location = response.headers.get("location")
            if not location or redirect_count >= max_redirects:
                raise PublicHttpMaterializationError("redirect_limit", "Redirect limit exceeded.")
            current = validate_public_url(urljoin(current, location))
            continue
        if response.status_code >= 400:
            raise PublicHttpMaterializationError("upstream_error", f"Source returned HTTP {response.status_code}.")
        content_type = str(response.headers.get("content-type", "")).split(";", 1)[0].strip().lower()
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise PublicHttpMaterializationError("unsupported_content_type", "Source content type is not supported.")
        body = bytes(response.content)
        if len(body) > max_body_bytes:
            raise PublicHttpMaterializationError("body_limit", "Source body exceeds the materialization limit.")
        return PublicHttpMaterialization(
            url=url,
            final_url=current,
            content_type=content_type,
            body=body,
            status_code=response.status_code,
        )
    raise PublicHttpMaterializationError("redirect_limit", "Redirect limit exceeded.")


class PublicHttpSourceMaterializer:
    """Facade class used by source-task adapters; no queue or DB ownership."""

    async def materialize(self, url: str, *, client: Any) -> PublicHttpMaterialization:
        return await materialize_public_http(url, client=client)


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "MAX_BODY_BYTES",
    "PublicHttpMaterialization",
    "PublicHttpMaterializationError",
    "PublicHttpSourceMaterializer",
    "materialize_public_http",
    "validate_public_url",
]
