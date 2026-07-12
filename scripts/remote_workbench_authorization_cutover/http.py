"""Bounded HTTP operations for the Remote Workbench cutover runner."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from .io import CutoverError


DEFAULT_RESPONSE_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 33_554_432


def _read_bounded(stream: Any, limit: int) -> bytes:
    if not isinstance(limit, int) or limit <= 0 or limit > MAX_RESPONSE_BYTES:
        raise CutoverError("HTTP response byte limit is invalid")
    body = stream.read(limit + 1)
    if len(body) > limit:
        raise CutoverError("HTTP response exceeded its byte limit")
    return body


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


@dataclass(frozen=True)
class HttpResponse:
    """Captured HTTP response with normalized lower-case headers."""

    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any]:
        """Decode an object response or fail closed."""

        try:
            payload = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CutoverError("HTTP response did not contain valid JSON") from error
        if not isinstance(payload, dict):
            raise CutoverError("HTTP response JSON must be an object")
        return payload


class HttpClient:
    """Make non-retrying HTTP calls with fixed timeouts."""

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 5.0,
        follow_redirects: bool = False,
        max_response_bytes: int = DEFAULT_RESPONSE_BYTES,
    ) -> HttpResponse:
        """Return one response without logging payloads or authorization headers."""

        body = None
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )
        opener = (
            urllib.request.build_opener()
            if follow_redirects
            else urllib.request.build_opener(_NoRedirect())
        )
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                status = int(response.status)
                return HttpResponse(
                    status=status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=b"" if status == 101 else _read_bounded(response, max_response_bytes),
                )
        except urllib.error.HTTPError as error:
            return HttpResponse(
                status=int(error.code),
                headers={key.lower(): value for key, value in error.headers.items()},
                body=_read_bounded(error, max_response_bytes),
            )
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CutoverError("HTTP request was unreachable") from error

    def get_json(
        self,
        url: str,
        *,
        timeout_seconds: float = 5.0,
        max_response_bytes: int = DEFAULT_RESPONSE_BYTES,
    ) -> dict[str, Any]:
        """GET one JSON object and require a 2xx response."""

        response = self.request(
            "GET",
            url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        if not 200 <= response.status < 300:
            raise CutoverError(f"HTTP GET failed with status {response.status}")
        return response.json()

    def put_json(
        self,
        url: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float = 10.0,
        max_response_bytes: int = DEFAULT_RESPONSE_BYTES,
    ) -> dict[str, Any]:
        """PUT one JSON object and require a 2xx response."""

        response = self.request(
            "PUT",
            url,
            payload=payload,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        if not 200 <= response.status < 300:
            raise CutoverError(f"HTTP PUT failed with status {response.status}")
        return response.json()
