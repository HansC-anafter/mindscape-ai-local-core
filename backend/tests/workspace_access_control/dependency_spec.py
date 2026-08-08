from starlette.requests import Request
import pytest

from backend.app.dependencies.auth import (
    AuthContext,
    _get_remote_gateway_identity,
)
from backend.app.dependencies.workspace_access import verified_identity_from_auth


def test_local_auth_maps_to_deterministic_local_binding():
    identity = verified_identity_from_auth(
        AuthContext(
            user_id="default-user",
            tenant_id="local",
            identity_provider="local",
            identity_issuer="local-core",
            identity_subject="default-user",
        )
    )
    assert identity.model_dump() == {
        "provider": "local",
        "issuer": "local-core",
        "subject": "default-user",
        "verified_email": None,
    }


def test_verified_cloud_claims_are_not_replaced_by_email():
    identity = verified_identity_from_auth(
        AuthContext(
            user_id="opaque-user",
            tenant_id="tenant",
            is_cloud_mode=True,
            identity_provider="cloudflare-access",
            identity_issuer="https://example.cloudflareaccess.com",
            identity_subject="subject-a",
            verified_email="person@example.com",
        )
    )
    assert identity.subject == "subject-a"
    assert identity.verified_email == "person@example.com"


def _request(headers, client=("127.0.0.1", 8300)):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/access-control/invitations/accept",
            "headers": [
                (key.lower().encode("ascii"), value.encode("ascii"))
                for key, value in headers.items()
            ],
            "client": client,
        }
    )


def test_loopback_gateway_headers_map_to_verified_identity():
    auth = _get_remote_gateway_identity(
        _request(
            {
                "x-mindscape-remote-ingress": "remote_workbench",
                "x-mindscape-identity-provider": "cloudflare-access",
                "x-mindscape-identity-issuer": (
                    "https://example.cloudflareaccess.com"
                ),
                "x-mindscape-identity-subject": "subject-a",
                "x-mindscape-identity-email": "PERSON@example.com",
            }
        ),
        include_workspace_ids=False,
    )
    assert auth is not None
    assert auth.identity_subject == "subject-a"
    assert auth.verified_email == "person@example.com"


def test_non_loopback_cannot_forge_gateway_identity():
    with pytest.raises(Exception) as caught:
        _get_remote_gateway_identity(
            _request(
                {"x-mindscape-remote-ingress": "remote_workbench"},
                client=("192.0.2.10", 443),
            ),
            include_workspace_ids=False,
        )
    assert getattr(caught.value, "status_code", None) == 403
