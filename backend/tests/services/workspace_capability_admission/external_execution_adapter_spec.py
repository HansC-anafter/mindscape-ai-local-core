from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.app.services.workspace_capability_admission.external_execution_adapter import (
    ExternalAuthorizationDenied,
    ExternalAuthorizationUnavailable,
    ExternalExecutionAuthorizationAdapter,
)
from backend.app.services.workspace_capability_admission.external_execution_contracts import (
    ExternalExecutionAuthorizationRequest,
    ExternalExecutionAuthorizationResponse,
    ExternalExecutionDecisionClaims,
    SignedExternalExecutionDecision,
)
from backend.app.services.workspace_capability_admission.external_execution_verifier import (
    ExternalDecisionTrustRoot,
    ExternalExecutionDecisionVerifier,
    canonical_json_bytes,
)


NOW = datetime.now(timezone.utc)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _request(**overrides):
    values = {
        "source_runtime_id": "runtime-one",
        "workspace_id": "workspace-one",
        "active_group_id": "group-one",
        "topology_snapshot_id": "topology-7",
        "topology_snapshot_hash": "1" * 64,
        "wpcs_hash": "2" * 64,
        "catalog_hash": "3" * 64,
        "product_surface_id": "instagram.workspace.references",
        "exact_capability_closure": [
            {
                "capability_key": "ig.references.read",
                "operation_type": "read",
            }
        ],
        "exact_pack_closure": [
            {
                "provider": "mindscape-cloud",
                "code": "ig",
                "version": "1.0.195",
                "source_sha256": "4" * 64,
            }
        ],
        "deployment_mode": "provider_managed",
        "dce_hash": "5" * 64,
        "trace_id": "trace-one",
        "root_execution_id": "execution-one",
        "request_deadline": NOW + timedelta(minutes=15),
    }
    values.update(overrides)
    return ExternalExecutionAuthorizationRequest.model_validate(values)


def _signed_response(private_key, request, *, allowed=True, deny_code=None):
    claims = ExternalExecutionDecisionClaims(
        media_type=(
            "application/vnd.mindscape."
            "external-execution-decision.v1+json"
        ),
        schema_version="mindscape.external-execution-decision.v1",
        issuer="mindscape-crs",
        audience=f"mindscape-local-core:{request.source_runtime_id}",
        decision_id="eed-one",
        allowed=allowed,
        deny_code=deny_code,
        source_runtime_id=request.source_runtime_id,
        workspace_id=request.workspace_id,
        active_group_id=request.active_group_id,
        topology_snapshot_id=request.topology_snapshot_id,
        topology_snapshot_hash=request.topology_snapshot_hash,
        wpcs_hash=request.wpcs_hash,
        catalog_hash=request.catalog_hash,
        product_surface_id=request.product_surface_id,
        exact_capability_closure=request.exact_capability_closure,
        exact_pack_closure=request.exact_pack_closure,
        deployment_mode=request.deployment_mode,
        dce_hash=request.dce_hash,
        risk=(
            {
                "max_risk_score": 2,
                "checked_capability_keys": ["ig.references.read"],
            }
            if allowed
            else None
        ),
        quota=(
            {
                "daily_remaining": 9,
                "monthly_remaining": 99,
                "lease_expires_at": NOW + timedelta(minutes=5),
            }
            if allowed
            else None
        ),
        provider=(
            {
                "provider_name": "openai",
                "api_url": "https://api.openai.com/v1",
                "token_type": "test",
                "access_token": "temporary",
                "token_id": "token-one",
                "token_expires_at": NOW + timedelta(minutes=5),
            }
            if allowed
            else None
        ),
        trace_id=request.trace_id,
        root_execution_id=request.root_execution_id,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
    )
    signed = SignedExternalExecutionDecision(
        claims=claims,
        alg="EdDSA",
        kid="key-one",
        signature=_b64url(
            private_key.sign(
                canonical_json_bytes(claims.model_dump(mode="json"))
            )
        ),
    )
    return ExternalExecutionAuthorizationResponse(
        decision=signed
    ).model_dump(mode="json")


def _verifier(private_key):
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return ExternalExecutionDecisionVerifier(
        [
            ExternalDecisionTrustRoot(
                issuer="mindscape-crs",
                kid="key-one",
                alg="EdDSA",
                public_key=_b64url(public),
                not_before=NOW - timedelta(days=1),
                not_after=NOW + timedelta(days=1),
            )
        ]
    )


@pytest.mark.asyncio
async def test_adapter_makes_one_exact_scoped_call_and_verifies_decision():
    private = Ed25519PrivateKey.generate()
    request = _request()
    calls = []

    def handler(http_request):
        calls.append(http_request)
        return httpx.Response(
            200,
            json=_signed_response(private, request),
        )

    client = httpx.AsyncClient(
        base_url="https://crs.test",
        transport=httpx.MockTransport(handler),
    )
    adapter = ExternalExecutionAuthorizationAdapter(
        base_url="https://crs.test",
        service_token="service-token",
        verifier=_verifier(private),
        http_client=client,
    )

    claims = await adapter.authorize_root(request)

    assert claims.allowed is True
    assert len(calls) == 1
    assert calls[0].url.path == (
        "/api/v1/crs/external-executions/authorize"
    )
    assert calls[0].headers["x-source-runtime-id"] == "runtime-one"
    assert calls[0].headers["x-workspace-id"] == "workspace-one"
    assert calls[0].headers["x-active-group-id"] == "group-one"
    await client.aclose()


@pytest.mark.asyncio
async def test_signed_deny_propagates_without_local_fallback():
    private = Ed25519PrivateKey.generate()
    request = _request()
    client = httpx.AsyncClient(
        base_url="https://crs.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json=_signed_response(
                    private,
                    request,
                    allowed=False,
                    deny_code="quota_exceeded",
                ),
            )
        ),
    )
    adapter = ExternalExecutionAuthorizationAdapter(
        base_url="https://crs.test",
        service_token="service-token",
        verifier=_verifier(private),
        http_client=client,
    )

    with pytest.raises(ExternalAuthorizationDenied, match="quota_exceeded"):
        await adapter.authorize_root(request)
    await client.aclose()


@pytest.mark.asyncio
async def test_tampered_or_unavailable_response_fails_closed():
    private = Ed25519PrivateKey.generate()
    request = _request()
    payload = _signed_response(private, request)
    payload["decision"]["claims"]["workspace_id"] = "other-workspace"
    client = httpx.AsyncClient(
        base_url="https://crs.test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=payload)
        ),
    )
    adapter = ExternalExecutionAuthorizationAdapter(
        base_url="https://crs.test",
        service_token="service-token",
        verifier=_verifier(private),
        http_client=client,
    )

    with pytest.raises(
        ExternalAuthorizationUnavailable,
        match="external_authorization_unavailable",
    ):
        await adapter.authorize_root(request)
    await client.aclose()
