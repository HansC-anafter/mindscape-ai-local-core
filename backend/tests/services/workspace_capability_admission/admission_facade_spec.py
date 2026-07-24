from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.deployment_control.contracts import (
    CeilingAssignment,
    EffectiveDeploymentCeiling,
)
from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
    verify_child_snapshot,
)
from backend.app.services.workspace_capability_admission.contracts import (
    AdmissionDenied,
    RootAdmissionRequest,
)
from backend.app.services.workspace_capability_admission.deployment_gate import (
    DeploymentGateOutcome,
)
from backend.app.services.workspace_capability_admission.external_execution_contracts import (
    ExternalExecutionDecisionClaims,
)
from backend.app.services.workspace_capability_admission.facade import (
    WorkspaceCapabilityAdmissionFacade,
)
from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupMember,
    WorkspaceGroupTopology,
    WorkspaceGroupTopologySnapshot,
)
from backend.app.services.workspace_product_configuration.contracts import (
    AdmissionConfigurationSource,
    EffectiveProductAssignment,
    WorkspaceCapabilitySetSnapshot,
)


NOW = datetime(2026, 7, 25, 0, 0, tzinfo=timezone.utc)
WORKSPACE_ID = "workspace-one"
GROUP_ID = "group-one"
SURFACE = "instagram.workspace.references"


def _wpcs(*, mode="enforced", assigned=True, host_ready=True):
    return WorkspaceCapabilitySetSnapshot(
        source_runtime_id="runtime-one",
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=GROUP_ID,
        topology_revision=7,
        topology_content_hash="1" * 64,
        catalog_hash="2" * 64,
        snapshot_hash="3" * 64,
        workspace_scope_revision=1 if mode != "legacy_unmanaged" else 0,
        group_scope_revision=0,
        workspace_admission_mode=mode,
        editable_scopes=["workspace"],
        scope_configurations=[],
        available_products=[],
        effective_assignments=(
            [
                EffectiveProductAssignment(
                    pcs_id="instagram_workspace_intelligence",
                    pcs_version="1.0.0",
                    product_surface_ids=[SURFACE],
                    configuration_sources=["workspace"],
                    host_ready=host_ready,
                )
            ]
            if assigned
            else []
        ),
    )


def _group_context():
    topology = WorkspaceGroupTopology(
        id=GROUP_ID,
        display_name="Sinnie Yoga Studio",
        owner_user_id="owner",
        revision=7,
        members=[
            WorkspaceGroupMember(
                workspace_id=WORKSPACE_ID,
                role="dispatch",
            )
        ],
    )
    return ActiveWorkspaceGroupContext(
        group_id=GROUP_ID,
        workspace_id=WORKSPACE_ID,
        role="dispatch",
        revision=7,
        topology=topology,
    )


def _product():
    return {
        "pcs_id": "instagram_workspace_intelligence",
        "version": "1.0.0",
        "product_surfaces": [
            {
                "id": SURFACE,
                "selectors": {"api_prefixes": ["/api/v1/ig"]},
            }
        ],
        "capability_keys": {
            "api_prefixes": ["/api/v1/ig"],
            "tool_keys": [],
            "playbook_codes": [],
        },
        "pack_closure": [
            {
                "provider": "mindscape-cloud",
                "code": "ig",
                "version": "1.0.195",
                "source_sha256": "4" * 64,
            }
        ],
    }


class FakeProducts:
    def __init__(self, *, mode="enforced", assigned=True, host_ready=True):
        self.calls = 0
        self.source = AdmissionConfigurationSource(
            snapshot=_wpcs(
                mode=mode,
                assigned=assigned,
                host_ready=host_ready,
            ),
            active_group_context=_group_context(),
            catalog_products=(_product(),),
        )

    def resolve_admission_source(self, **_):
        self.calls += 1
        return self.source


class FakeDeployment:
    def __init__(self, *, mode="unmanaged_local", permitted=True):
        self.calls = 0
        self.mode = mode
        self.permitted = permitted

    def evaluate(self, **_):
        self.calls += 1
        return DeploymentGateOutcome(
            ceiling=EffectiveDeploymentCeiling(
                mode=self.mode,
                provider_code=(
                    "site-hub" if self.mode == "provider_managed" else None
                ),
                state_revision=2,
                envelope_revision=(
                    4 if self.mode == "provider_managed" else None
                ),
                envelope_hash=(
                    "5" * 64
                    if self.mode == "provider_managed"
                    else None
                ),
                assignments=[
                    CeilingAssignment(
                        pcs_id="instagram_workspace_intelligence",
                        pcs_version="1.0.0",
                        allowed_surface_ids=[SURFACE],
                    )
                ],
            ),
            permitted=self.permitted,
        )


class FakeSnapshots:
    def __init__(self, order=None):
        self.calls = 0
        self.order = order

    def get_or_create(self, context, *, actor_user_id):
        self.calls += 1
        if self.order is not None:
            self.order.append("gate0")
        return WorkspaceGroupTopologySnapshot(
            id="topology-one",
            group_id=context.group_id,
            display_name=context.topology.display_name,
            group_revision=context.revision,
            content_hash="1" * 64,
            members=context.topology.members,
            created_by_user_id=actor_user_id,
            created_at=NOW,
        )


class FakeExternal:
    def __init__(self, order=None):
        self.calls = []
        self.order = order

    async def authorize_root(self, request):
        self.calls.append(request)
        if self.order is not None:
            self.order.append("eed")
        return ExternalExecutionDecisionClaims(
            media_type=(
                "application/vnd.mindscape."
                "external-execution-decision.v1+json"
            ),
            schema_version="mindscape.external-execution-decision.v1",
            issuer="mindscape-crs",
            audience="mindscape-local-core:runtime-one",
            decision_id="eed-one",
            allowed=True,
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
            risk={
                "max_risk_score": 1,
                "checked_capability_keys": [request.selector_key]
                if hasattr(request, "selector_key")
                else ["/api/v1/ig/references"],
            },
            quota={
                "daily_remaining": 9,
                "monthly_remaining": 99,
                "lease_expires_at": NOW + timedelta(minutes=5),
            },
            provider={
                "provider_name": "provider",
                "api_url": "https://provider.test",
                "token_type": "bearer",
                "access_token": "secret-not-persisted",
                "token_id": "token-one",
                "token_expires_at": NOW + timedelta(minutes=5),
            },
            trace_id=request.trace_id,
            root_execution_id=request.root_execution_id,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )


def _request(**overrides):
    values = {
        "workspace_id": WORKSPACE_ID,
        "explicit_active_group_id": GROUP_ID,
        "observed_topology_revision": 7,
        "product_surface_id": SURFACE,
        "selector_kind": "api_prefix",
        "selector_key": "/api/v1/ig/references",
        "operation_type": "read",
        "entry": "local",
        "execution_backend": "local",
        "actor_user_id": "owner",
        "allowed_workspace_ids": [WORKSPACE_ID],
        "allowed_group_ids": [GROUP_ID],
        "trace_id": "trace-one",
        "root_execution_id": "root-one",
    }
    values.update(overrides)
    return RootAdmissionRequest.model_validate(values)


def _facade(products, deployment=None, snapshots=None, external=None):
    return WorkspaceCapabilityAdmissionFacade(
        workspace_product_facade=products,
        deployment_gate=deployment or FakeDeployment(),
        topology_snapshot_service=snapshots or FakeSnapshots(),
        external_adapter=external or FakeExternal(),
        now=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_local_root_resolves_once_and_child_only_verifies_snapshot():
    products = FakeProducts()
    deployment = FakeDeployment()
    snapshots = FakeSnapshots()
    external = FakeExternal()

    result = await _facade(
        products,
        deployment,
        snapshots,
        external,
    ).admit_root(_request())

    assert result.snapshot.availability == "available"
    assert products.calls == 1
    assert deployment.calls == 1
    assert snapshots.calls == 1
    assert external.calls == []
    verified = verify_child_snapshot(
        result.snapshot.model_dump(mode="json"),
        expected_workspace_id=WORKSPACE_ID,
        expected_root_execution_id="root-one",
    )
    assert verified.snapshot_hash == result.snapshot.snapshot_hash
    assert products.calls == 1


@pytest.mark.asyncio
async def test_configuration_only_preserves_unconfigured_local_root():
    products = FakeProducts(mode="configuration_only", assigned=False)
    result = await _facade(products).admit_root(_request())
    assert result.snapshot.availability == "not_configured"
    assert result.snapshot.admission_mode == "configuration_only"


@pytest.mark.asyncio
async def test_enforced_rejects_before_deployment_or_topology_write():
    products = FakeProducts(mode="enforced", assigned=False)
    deployment = FakeDeployment()
    snapshots = FakeSnapshots()
    with pytest.raises(AdmissionDenied, match="not_configured"):
        await _facade(
            products,
            deployment,
            snapshots,
        ).admit_root(_request())
    assert products.calls == 1
    assert deployment.calls == 0
    assert snapshots.calls == 0


@pytest.mark.asyncio
async def test_remote_requires_trusted_gateway_marker_in_every_mode():
    products = FakeProducts(mode="configuration_only")
    with pytest.raises(AdmissionDenied, match="remote_not_exposed"):
        await _facade(products).admit_root(
            _request(entry="remote", remote_ingress_verified=False)
        )


@pytest.mark.asyncio
async def test_provider_ceiling_is_hard_even_in_shadow():
    products = FakeProducts(mode="shadow")
    with pytest.raises(AdmissionDenied, match="deployment_not_permitted"):
        await _facade(
            products,
            FakeDeployment(mode="provider_managed", permitted=False),
        ).admit_root(_request())


@pytest.mark.asyncio
async def test_shadow_records_bounded_in_process_outcome():
    from backend.app.services.workspace_capability_admission.outcome_metrics import (
        shadow_outcome_snapshot,
    )

    before = shadow_outcome_snapshot().get("available", 0)
    await _facade(FakeProducts(mode="shadow")).admit_root(_request())
    assert shadow_outcome_snapshot()["available"] == before + 1


@pytest.mark.asyncio
async def test_external_root_creates_gate0_then_sends_one_exact_capability():
    order = []
    external = FakeExternal(order)
    result = await _facade(
        FakeProducts(),
        FakeDeployment(mode="provider_managed"),
        FakeSnapshots(order),
        external,
    ).admit_root(_request(execution_backend="external_provider"))

    assert order == ["gate0", "eed"]
    assert len(external.calls) == 1
    request = external.calls[0]
    assert len(request.exact_capability_closure) == 1
    assert request.exact_capability_closure[0].capability_key == (
        "/api/v1/ig/references"
    )
    assert len(request.exact_pack_closure) == 1
    serialized = result.snapshot.model_dump(mode="json")
    assert "secret-not-persisted" not in str(serialized)
    assert result.snapshot.provider_token_id == "token-one"


def test_child_snapshot_tamper_fails_closed():
    from backend.app.services.workspace_capability_admission.execution_snapshot import (
        build_execution_snapshot,
    )

    snapshot = build_execution_snapshot(
        {
            "source_runtime_id": "runtime-one",
            "workspace_id": WORKSPACE_ID,
            "active_group_id": None,
            "topology_snapshot_id": None,
            "topology_snapshot_hash": None,
            "wpcs_hash": "3" * 64,
            "catalog_hash": "2" * 64,
            "admission_mode": "legacy_unmanaged",
            "pcs_id": None,
            "pcs_version": None,
            "product_surface_id": SURFACE,
            "selector_kind": "api_prefix",
            "selector_key": "/api/v1/ig/references",
            "operation_type": "read",
            "entry": "local",
            "execution_backend": "local",
            "deployment_mode": "unmanaged_local",
            "deployment_state_revision": 0,
            "deployment_envelope_revision": None,
            "dce_hash": None,
            "availability": "not_configured",
            "diagnostics": [],
            "external_decision_id": None,
            "external_decision_issuer": None,
            "external_decision_expires_at": None,
            "provider_token_id": None,
            "trace_id": "trace-one",
            "root_execution_id": "root-one",
            "admitted_at": NOW,
        }
    )
    payload = snapshot.model_dump(mode="json")
    payload["workspace_id"] = "tampered"
    with pytest.raises(ValueError, match="hash_mismatch"):
        verify_child_snapshot(
            payload,
            expected_workspace_id=WORKSPACE_ID,
            expected_root_execution_id="root-one",
        )
