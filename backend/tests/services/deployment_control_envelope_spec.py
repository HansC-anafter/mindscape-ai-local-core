from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.app.services.deployment_control.contracts import (
    DeploymentCapabilityEnvelopeClaims,
    DeploymentControlState,
    EnvelopePackRef,
    EnvelopeProductGrant,
    SignedDeploymentCapabilityEnvelope,
)
from backend.app.services.deployment_control.effective_ceiling import (
    intersect_effective_ceiling,
)
from backend.app.services.deployment_control.envelope_verifier import (
    DeploymentEnvelopeVerifier,
    canonical_json_bytes,
)
from backend.app.services.deployment_control.errors import (
    DeploymentEnvelopeExpired,
    DeploymentEnvelopeInvalid,
    DeploymentTrustRootMissing,
)
from backend.app.services.deployment_control.trust_store import (
    DeploymentTrustRoot,
    DeploymentTrustStore,
)
from backend.app.services.workspace_product_configuration.contracts import (
    EffectiveProductAssignment,
    WorkspaceCapabilitySetSnapshot,
)


NOW = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
CATALOG_HASH = "a" * 64
RUNTIME_ID = "runtime-one"
AUDIENCE = f"mindscape-local-core:{RUNTIME_ID}"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _key_pair():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, _b64url(public_key)


def _claims() -> DeploymentCapabilityEnvelopeClaims:
    return DeploymentCapabilityEnvelopeClaims(
        media_type=(
            "application/vnd.mindscape."
            "deployment-capability-envelope.v1+json"
        ),
        schema_version="mindscape.deployment-capability-envelope.v1",
        issuer="site-hub",
        audience=AUDIENCE,
        provider_code="site_hub",
        source_runtime_id=RUNTIME_ID,
        tenant_id="tenant-one",
        site_id="site-one",
        catalog_hash=CATALOG_HASH,
        issued_at=NOW - timedelta(minutes=2),
        not_before=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=1),
        envelope_revision=1,
        allowed_products=[
            EnvelopeProductGrant(
                pcs_id="instagram_workspace_intelligence",
                pcs_version="1.0.0",
                surface_ids=["instagram.workspace.references"],
                pack_closure=[
                    EnvelopePackRef(
                        provider="mindscape-cloud",
                        code="ig",
                        version="1.0.195",
                    )
                ],
            )
        ],
    )


def _signed(private_key, *, kid="key-one", claims=None):
    claims = claims or _claims()
    signature = private_key.sign(
        canonical_json_bytes(claims.model_dump(mode="json"))
    )
    return SignedDeploymentCapabilityEnvelope(
        claims=claims,
        alg="EdDSA",
        kid=kid,
        signature=_b64url(signature),
    )


def _verifier(public_key, *, kid="key-one", not_after=None):
    return DeploymentEnvelopeVerifier(
        DeploymentTrustStore(
            [
                DeploymentTrustRoot(
                    issuer="site-hub",
                    kid=kid,
                    alg="EdDSA",
                    public_key=public_key,
                    not_before=NOW - timedelta(days=1),
                    not_after=not_after or NOW + timedelta(days=1),
                )
            ]
        )
    )


def test_ed25519_envelope_verifies_with_exact_runtime_catalog_and_audience():
    private_key, public_key = _key_pair()
    envelope = _signed(private_key)

    digest = _verifier(public_key).verify(
        envelope,
        expected_audience=AUDIENCE,
        expected_source_runtime_id=RUNTIME_ID,
        expected_catalog_hash=CATALOG_HASH,
        now=NOW,
    )

    assert len(digest) == 64


def test_tamper_expiry_and_unknown_kid_fail_closed():
    private_key, public_key = _key_pair()
    envelope = _signed(private_key)
    tampered_payload = envelope.model_dump(mode="json")
    tampered_payload["claims"]["site_id"] = "other-site"
    tampered = SignedDeploymentCapabilityEnvelope.model_validate(
        tampered_payload
    )

    with pytest.raises(DeploymentEnvelopeInvalid):
        _verifier(public_key).verify(
            tampered,
            expected_audience=AUDIENCE,
            expected_source_runtime_id=RUNTIME_ID,
            expected_catalog_hash=CATALOG_HASH,
            now=NOW,
        )
    with pytest.raises(DeploymentEnvelopeExpired):
        _verifier(public_key).verify(
            envelope,
            expected_audience=AUDIENCE,
            expected_source_runtime_id=RUNTIME_ID,
            expected_catalog_hash=CATALOG_HASH,
            now=NOW + timedelta(hours=2),
        )
    with pytest.raises(DeploymentTrustRootMissing):
        _verifier(public_key, kid="other-key").verify(
            envelope,
            expected_audience=AUDIENCE,
            expected_source_runtime_id=RUNTIME_ID,
            expected_catalog_hash=CATALOG_HASH,
            now=NOW,
        )


def test_rotation_overlap_accepts_explicit_old_and_new_keys_only():
    old_private, old_public = _key_pair()
    new_private, new_public = _key_pair()
    trust_store = DeploymentTrustStore(
        [
            DeploymentTrustRoot(
                issuer="site-hub",
                kid="old",
                alg="EdDSA",
                public_key=old_public,
                not_before=NOW - timedelta(days=2),
                not_after=NOW + timedelta(minutes=5),
            ),
            DeploymentTrustRoot(
                issuer="site-hub",
                kid="new",
                alg="EdDSA",
                public_key=new_public,
                not_before=NOW - timedelta(minutes=5),
                not_after=NOW + timedelta(days=2),
            ),
        ]
    )
    verifier = DeploymentEnvelopeVerifier(trust_store)

    for envelope in (
        _signed(old_private, kid="old"),
        _signed(new_private, kid="new"),
    ):
        verifier.verify(
            envelope,
            expected_audience=AUDIENCE,
            expected_source_runtime_id=RUNTIME_ID,
            expected_catalog_hash=CATALOG_HASH,
            now=NOW,
        )
    with pytest.raises(DeploymentTrustRootMissing):
        verifier.verify(
            _signed(old_private, kid="old"),
            expected_audience=AUDIENCE,
            expected_source_runtime_id=RUNTIME_ID,
            expected_catalog_hash=CATALOG_HASH,
            now=NOW + timedelta(minutes=10),
        )


def _wpcs() -> WorkspaceCapabilitySetSnapshot:
    return WorkspaceCapabilitySetSnapshot(
        source_runtime_id=RUNTIME_ID,
        workspace_id="workspace-one",
        catalog_hash=CATALOG_HASH,
        snapshot_hash="b" * 64,
        workspace_scope_revision=1,
        group_scope_revision=0,
        workspace_admission_mode="configuration_only",
        editable_scopes=["workspace"],
        scope_configurations=[],
        available_products=[],
        effective_assignments=[
            EffectiveProductAssignment(
                pcs_id="instagram_workspace_intelligence",
                pcs_version="1.0.0",
                product_surface_ids=[
                    "instagram.workspace.references",
                    "instagram.workspace.publish",
                ],
                configuration_sources=["workspace"],
                host_ready=True,
            ),
            EffectiveProductAssignment(
                pcs_id="adaptive_learning_teach_back",
                pcs_version="1.0.0",
                product_surface_ids=["adaptive_learning.workbench"],
                configuration_sources=["workspace"],
                host_ready=True,
            ),
        ],
    )


def test_provider_ceiling_intersection_never_expands_wpcs():
    private_key, _public_key = _key_pair()
    state = DeploymentControlState(
        mode="provider_managed",
        provider_code="site_hub",
        signed_envelope=_signed(private_key),
        envelope_hash="c" * 64,
        issuer="site-hub",
        key_id="key-one",
        expires_at=NOW + timedelta(hours=1),
        envelope_revision=1,
        state_revision=4,
    )

    ceiling = intersect_effective_ceiling(_wpcs(), state)

    assert [item.pcs_id for item in ceiling.assignments] == [
        "instagram_workspace_intelligence"
    ]
    assert ceiling.assignments[0].allowed_surface_ids == [
        "instagram.workspace.references"
    ]


def test_unmanaged_ceiling_preserves_every_configured_surface():
    ceiling = intersect_effective_ceiling(
        _wpcs(),
        DeploymentControlState(mode="unmanaged_local", state_revision=0),
    )

    assert len(ceiling.assignments) == 2
    assert ceiling.assignments[0].allowed_surface_ids == [
        "instagram.workspace.publish",
        "instagram.workspace.references",
    ]
