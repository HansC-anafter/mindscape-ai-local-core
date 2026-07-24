from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.deployment_control.contracts import (
    DeploymentCapabilityEnvelopeClaims,
    DeploymentControlState,
    EnvelopePackRef,
    EnvelopeProductGrant,
    ReplaceDeploymentControlCommand,
    SignedDeploymentCapabilityEnvelope,
)
from backend.app.services.deployment_control.errors import (
    DeploymentControlStateRevisionConflict,
)
from backend.app.services.deployment_control.facade import DeploymentControlFacade


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)
CATALOG_HASH = "a" * 64


def _envelope(revision=1):
    return SignedDeploymentCapabilityEnvelope(
        claims=DeploymentCapabilityEnvelopeClaims(
            media_type=(
                "application/vnd.mindscape."
                "deployment-capability-envelope.v1+json"
            ),
            schema_version="mindscape.deployment-capability-envelope.v1",
            issuer="alternate-provider",
            audience="mindscape-local-core:runtime-one",
            provider_code="alternate",
            source_runtime_id="runtime-one",
            tenant_id="tenant-one",
            site_id="site-one",
            catalog_hash=CATALOG_HASH,
            issued_at=NOW - timedelta(minutes=2),
            not_before=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
            envelope_revision=revision,
            allowed_products=[
                EnvelopeProductGrant(
                    pcs_id="adaptive_learning_teach_back",
                    pcs_version="1.0.0",
                    surface_ids=["adaptive_learning.workbench"],
                    pack_closure=[
                        EnvelopePackRef(
                            provider="mindscape-cloud",
                            code="adaptive_learning",
                            version="0.1.3",
                        )
                    ],
                )
            ],
        ),
        alg="EdDSA",
        kid="alternate-key",
        signature="a" * 86,
    )


class FakeVerifier:
    def __init__(self):
        self.calls = []

    def verify(self, envelope, **kwargs):
        self.calls.append((envelope, kwargs))
        return "b" * 64


class FakeRepository:
    def __init__(self):
        self.state = DeploymentControlState(
            mode="unmanaged_local",
            state_revision=0,
        )
        self.replacements = []

    def get_active_catalog_hash(self):
        return CATALOG_HASH

    def get_state(self):
        return self.state

    def replace(self, **kwargs):
        self.replacements.append(kwargs)
        expected = kwargs["expected_state_revision"]
        if expected != self.state.state_revision:
            raise DeploymentControlStateRevisionConflict(
                expected,
                self.state.state_revision,
            )
        if (
            kwargs["envelope_hash"] == self.state.envelope_hash
            and kwargs["mode"] == self.state.mode
        ):
            return self.state, False
        envelope = kwargs["envelope"]
        self.state = DeploymentControlState(
            mode=kwargs["mode"],
            provider_code=kwargs["provider_code"],
            signed_envelope=envelope,
            envelope_hash=kwargs["envelope_hash"],
            issuer=envelope.claims.issuer if envelope else None,
            key_id=envelope.kid if envelope else None,
            expires_at=envelope.claims.expires_at if envelope else None,
            envelope_revision=(
                envelope.claims.envelope_revision if envelope else None
            ),
            state_revision=self.state.state_revision + 1,
            updated_by=kwargs["actor_user_id"],
        )
        return self.state, True


def test_facade_is_provider_neutral_and_replacement_is_idempotent():
    repository = FakeRepository()
    verifier = FakeVerifier()
    facade = DeploymentControlFacade(
        repository=repository,
        verifier=verifier,
        runtime_id="runtime-one",
    )
    command = ReplaceDeploymentControlCommand(
        expected_state_revision=0,
        mode="provider_managed",
        provider_code="alternate",
        signed_envelope=_envelope(),
    )

    first = facade.replace(command, actor_user_id="operator", now=NOW)
    replay = facade.replace(
        command.model_copy(update={"expected_state_revision": 1}),
        actor_user_id="operator",
        now=NOW,
    )

    assert first.replaced is True
    assert replay.replaced is False
    assert first.state.provider_code == "alternate"
    assert len(verifier.calls) == 2


def test_unmanaged_replace_does_not_resolve_provider_or_trust_root():
    repository = FakeRepository()
    verifier = FakeVerifier()
    facade = DeploymentControlFacade(
        repository=repository,
        verifier=verifier,
        runtime_id="runtime-one",
    )

    result = facade.replace(
        ReplaceDeploymentControlCommand(
            expected_state_revision=0,
            mode="unmanaged_local",
        ),
        actor_user_id="operator",
        now=NOW,
    )

    assert result.replaced is False
    assert verifier.calls == []


def test_state_revision_conflict_is_not_retried():
    repository = FakeRepository()
    facade = DeploymentControlFacade(
        repository=repository,
        verifier=FakeVerifier(),
        runtime_id="runtime-one",
    )

    with pytest.raises(DeploymentControlStateRevisionConflict):
        facade.replace(
            ReplaceDeploymentControlCommand(
                expected_state_revision=2,
                mode="unmanaged_local",
            ),
            actor_user_id="operator",
            now=NOW,
        )
