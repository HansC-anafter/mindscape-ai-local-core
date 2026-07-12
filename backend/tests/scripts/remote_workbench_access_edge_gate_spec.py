from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.edge import AccessEdgeGate
from remote_workbench_authorization_cutover.http import HttpResponse
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.secure_inputs import (
    EXPECTED_AUDIENCE,
    EXPECTED_ISSUER,
)


NOW = 2_000_000_000


def _segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _certificate(private_key) -> str:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "access.test")])
    moment = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(moment - timedelta(days=1))
        .not_valid_after(moment + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _meta(private_key, *, exp: int = NOW + 300) -> str:
    header = _segment({"alg": "RS256", "kid": "cert-key"})
    claims = _segment(
        {
            "aud": [EXPECTED_AUDIENCE],
            "hostname": "remote-workbench.mindscapeai.app",
            "type": "meta",
            "redirect_url": "/",
            "iat": NOW - 5,
            "nbf": NOW - 5,
            "exp": exp,
        }
    )
    signing_input = f"{header}.{claims}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{header}.{claims}.{encoded}"


class EdgeHttp:
    def __init__(self, location: str, cert: str) -> None:
        self.location = location
        self.cert = cert
        self.requests: list[dict] = []
        self.cert_gets = 0
        self.cert_kwargs: dict = {}

    def request(self, method, url, **kwargs) -> HttpResponse:
        self.requests.append({"method": method, "url": url, **kwargs})
        return HttpResponse(302, {"location": self.location}, b"")

    def get_json(self, url, **kwargs) -> dict:
        self.cert_gets += 1
        self.cert_kwargs = kwargs
        assert url == f"{EXPECTED_ISSUER}/cdn-cgi/access/certs"
        return {
            "keys": [],
            "public_cert": self.cert,
            "public_certs": [{"kid": "cert-key", "cert": self.cert}],
        }


def _location(meta: str, *, kid: str = EXPECTED_AUDIENCE) -> str:
    query = urlencode({"kid": kid, "redirect_url": "/", "meta": meta})
    return (
        f"{EXPECTED_ISSUER}/cdn-cgi/access/login/"
        f"remote-workbench.mindscapeai.app?{query}"
    )


def test_access_edge_gate_verifies_exact_redirect_and_signed_meta() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    http = EdgeHttp(_location(_meta(private_key)), _certificate(private_key))

    AccessEdgeGate(http, now=lambda: NOW).verify()

    assert http.cert_gets == 1
    assert http.cert_kwargs["max_response_bytes"] == 65_536
    assert http.requests == [
        {
            "method": "GET",
            "url": "https://remote-workbench.mindscapeai.app/",
            "timeout_seconds": 5.0,
            "follow_redirects": False,
        }
    ]


def test_access_edge_gate_rejects_wrong_audience_before_certificate_fetch() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    http = EdgeHttp(_location(_meta(private_key), kid="wrong-audience"), _certificate(private_key))

    with pytest.raises(CutoverError, match="redirect contract"):
        AccessEdgeGate(http, now=lambda: NOW).verify()
    assert http.cert_gets == 0


def test_access_edge_gate_rejects_bad_signature_and_expired_meta() -> None:
    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_signature = EdgeHttp(_location(_meta(signing_key)), _certificate(other_key))
    with pytest.raises(CutoverError, match="signature verification"):
        AccessEdgeGate(bad_signature, now=lambda: NOW).verify()

    expired = EdgeHttp(_location(_meta(signing_key, exp=NOW - 61)), _certificate(signing_key))
    with pytest.raises(CutoverError, match="claims verification"):
        AccessEdgeGate(expired, now=lambda: NOW).verify()
