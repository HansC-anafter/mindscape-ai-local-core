"""Cloudflare Access edge pre-mutation verification."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .http import HttpClient
from .io import CutoverError
from .secure_inputs import EXPECTED_AUDIENCE, EXPECTED_ISSUER


PUBLIC_ORIGIN = "https://remote-workbench.mindscapeai.app"
PUBLIC_HOSTNAME = "remote-workbench.mindscapeai.app"


def _decode_segment(value: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CutoverError("Cloudflare Access meta token is malformed") from error
    if not isinstance(payload, dict):
        raise CutoverError("Cloudflare Access meta token is malformed")
    return payload


class AccessEdgeGate:
    """Verify Access redirect metadata against the live team certificate set."""

    def __init__(
        self,
        http: HttpClient,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.http = http
        self.now = now

    @staticmethod
    def _public_key(pem: str) -> Any:
        encoded = pem.encode("utf-8")
        try:
            return x509.load_pem_x509_certificate(encoded).public_key()
        except ValueError:
            try:
                return serialization.load_pem_public_key(encoded)
            except ValueError as error:
                raise CutoverError("Cloudflare Access certificate is malformed") from error

    @staticmethod
    def _matching_certificate(certs: Mapping[str, Any], key_id: str) -> str:
        values = certs.get("public_certs")
        if not isinstance(values, list):
            raise CutoverError("Cloudflare Access certificate response is malformed")
        matches = [
            item.get("cert")
            for item in values
            if isinstance(item, Mapping)
            and item.get("kid") == key_id
            and isinstance(item.get("cert"), str)
        ]
        if len(matches) != 1 or not matches[0].strip():
            raise CutoverError("Cloudflare Access meta signing certificate is unavailable")
        return matches[0]

    def verify(self) -> None:
        """Require one exact signed Access login redirect before any mutation."""

        redirect = self.http.request(
            "GET",
            f"{PUBLIC_ORIGIN}/",
            timeout_seconds=5.0,
            follow_redirects=False,
        )
        location = redirect.headers.get("location")
        if redirect.status != 302 or not location:
            raise CutoverError("Cloudflare Access login redirect is unavailable")
        parsed = urlparse(location)
        issuer = urlparse(EXPECTED_ISSUER)
        expected_path = f"/cdn-cgi/access/login/{PUBLIC_HOSTNAME}"
        query = parse_qs(parsed.query, keep_blank_values=True)
        if (
            parsed.scheme != "https"
            or parsed.netloc != issuer.netloc
            or parsed.path != expected_path
            or set(query) != {"kid", "redirect_url", "meta"}
            or query.get("kid") != [EXPECTED_AUDIENCE]
            or query.get("redirect_url") != ["/"]
            or len(query.get("meta") or []) != 1
            or not query["meta"][0]
        ):
            raise CutoverError("Cloudflare Access login redirect contract mismatch")
        token = query["meta"][0]
        parts = token.split(".")
        if len(parts) != 3 or not all(parts):
            raise CutoverError("Cloudflare Access meta token is malformed")
        header = _decode_segment(parts[0])
        claims = _decode_segment(parts[1])
        key_id = str(header.get("kid") or "")
        if header.get("alg") != "RS256" or not key_id:
            raise CutoverError("Cloudflare Access meta signing header mismatch")
        certs = self.http.get_json(
            f"{EXPECTED_ISSUER}/cdn-cgi/access/certs",
            timeout_seconds=5.0,
            max_response_bytes=65_536,
        )
        public_key = self._public_key(self._matching_certificate(certs, key_id))
        try:
            signature = base64.urlsafe_b64decode(
                parts[2] + "=" * ((4 - len(parts[2]) % 4) % 4)
            )
            public_key.verify(
                signature,
                f"{parts[0]}.{parts[1]}".encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except (ValueError, InvalidSignature) as error:
            raise CutoverError("Cloudflare Access meta signature verification failed") from error
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        now = int(self.now())
        times = [claims.get(name) for name in ("iat", "nbf", "exp")]
        if (
            audiences != [EXPECTED_AUDIENCE]
            or claims.get("hostname") != PUBLIC_HOSTNAME
            or claims.get("type") != "meta"
            or claims.get("redirect_url") != "/"
            or not all(type(value) is int for value in times)
            or claims["iat"] > now + 60
            or claims["nbf"] > now + 60
            or claims["exp"] <= now - 60
            or claims["iat"] > claims["exp"]
            or claims["nbf"] > claims["exp"]
        ):
            raise CutoverError("Cloudflare Access meta claims verification failed")
