from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupMember,
    WorkspaceGroupTopology,
)
from backend.app.services.workspace_product_configuration.catalog_artifact import (
    verify_catalog_artifact,
)
from backend.app.services.workspace_product_configuration.contracts import (
    ReplaceScopeCommand,
)
from backend.app.services.workspace_product_configuration.errors import (
    CatalogArtifactInvalidError,
    TopologyRevisionConflictError,
    TopologyRevisionRequiredError,
    WorkspaceProductConfigurationError,
    WorkspaceProductSnapshotLimitError,
)
from backend.app.services.workspace_product_configuration.facade import (
    WorkspaceProductConfigurationFacade,
)


WORKSPACE_ID = "ws-1"
GROUP_ID = "wg-1"
CATALOG_HASH_PLACEHOLDER = "0" * 64


def _canonical(payload) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _artifact() -> dict:
    catalog = {
        "catalog_id": "test.catalog",
        "catalog_version": 1,
        "products": [
            {
                "pcs_id": "instagram_workspace_intelligence",
                "version": "1.0.0",
                "display_name": "Instagram Workspace Intelligence",
                "outcome_summary": "Govern workspace references.",
                "semantic_contract": "docs/contract.md",
                "root_packs": [{"code": "ig", "version": "1.0.195"}],
                "product_surfaces": [
                    {
                        "id": "instagram.workspace.references",
                        "display_name": "Instagram References",
                        "selectors": {"api_prefixes": ["/api/v1/ig"]},
                    }
                ],
                "pack_closure": [
                    {
                        "provider": "mindscape-cloud",
                        "code": "ig",
                        "version": "1.0.195",
                        "source_sha256": "2" * 64,
                    }
                ],
                "capability_keys": {
                    "api_prefixes": ["/api/v1/ig"],
                    "tool_keys": [],
                    "playbook_codes": [],
                },
                "contracts": [],
                "ui_surfaces": [],
            }
        ],
        "reverse_indexes": {},
    }
    catalog_hash = sha256(_canonical(catalog)).hexdigest()
    unsigned = {
        "media_type": (
            "application/vnd.mindscape.product-capability-catalog.v1+json"
        ),
        "schema_version": "mindscape.product-capability-catalog.v1",
        "catalog_hash": catalog_hash,
        "source_commit": "1" * 40,
        "compiler_version": "1.0.0",
        "generated_by": "test",
        "catalog": catalog,
    }
    return {
        **unsigned,
        "artifact_hash": sha256(_canonical(unsigned)).hexdigest(),
    }


def _artifact_with_host_requirement() -> dict:
    artifact = _artifact()
    artifact["catalog"]["products"][0]["pack_closure"][0][
        "host_requirements"
    ] = [
        {
            "requirement_code": "ig_host_automation",
            "operations": ["watch-screenshots"],
        }
    ]
    artifact["catalog_hash"] = sha256(
        _canonical(artifact["catalog"])
    ).hexdigest()
    unsigned = {
        key: value for key, value in artifact.items() if key != "artifact_hash"
    }
    artifact["artifact_hash"] = sha256(_canonical(unsigned)).hexdigest()
    return artifact


def _state(*, workspace_scope=None, group_scope=None) -> dict:
    artifact = _artifact()
    scopes = [
        scope for scope in (workspace_scope, group_scope) if scope is not None
    ]
    return {
        "artifact_hash": artifact["artifact_hash"],
        "catalog_hash": artifact["catalog_hash"],
        "source_commit": artifact["source_commit"],
        "compiler_version": artifact["compiler_version"],
        "artifact": artifact,
        "readiness": {"ig": {"enabled": True, "version": "1.0.195"}},
        "scopes": scopes,
    }


def _scope(kind: str, scope_id: str, *, revision=1, mode=None):
    artifact = _artifact()
    return {
        "scope_kind": kind,
        "scope_id": scope_id,
        "catalog_hash": artifact["catalog_hash"],
        "revision": revision,
        "admission_mode": mode,
        "assignments": [
            {
                "pcs_id": "instagram_workspace_intelligence",
                "pcs_version": "1.0.0",
            }
        ],
    }


def _context(owner="owner") -> ActiveWorkspaceGroupContext:
    topology = WorkspaceGroupTopology(
        id=GROUP_ID,
        display_name="Sinnie Yoga Studio Group",
        owner_user_id=owner,
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


class FakeGroupFacade:
    def __init__(self, context=None):
        self.context = context
        self.calls = 0

    def resolve_context(self, **kwargs):
        self.calls += 1
        return self.context if kwargs["active_group_id"] else None


class FakeRepository:
    def __init__(self, state):
        self.state = state
        self.effective_reads = 0
        self.writes = []
        self.imports = []

    def load_effective_state(self, **kwargs):
        self.effective_reads += 1
        return deepcopy(self.state)

    def replace_scope(self, **kwargs):
        self.writes.append(kwargs)
        return {
            "scope_kind": kwargs["scope_kind"],
            "scope_id": kwargs["scope_id"],
            "revision": kwargs["expected_revision"] + 1,
            "catalog_hash": kwargs["catalog_hash"],
            "admission_mode": kwargs["admission_mode"],
            "assignments": kwargs["assignments"],
        }

    def import_catalog(self, artifact, *, actor_user_id):
        self.imports.append((artifact, actor_user_id))
        return True


def _facade(repository, group_facade=None):
    return WorkspaceProductConfigurationFacade(
        repository=repository,
        workspace_group_facade=group_facade or FakeGroupFacade(),
        runtime_id="device-test",
    )


def test_absent_scope_projects_legacy_without_topology_write() -> None:
    repository = FakeRepository(_state())
    group_facade = FakeGroupFacade()

    snapshot = _facade(repository, group_facade).resolve_snapshot(
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=None,
        observed_topology_revision=None,
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
    )

    assert snapshot.workspace_admission_mode == "legacy_unmanaged"
    assert snapshot.workspace_scope_revision == 0
    assert snapshot.effective_assignments == []
    assert repository.effective_reads == 1
    assert group_facade.calls == 1


def test_admission_source_returns_wpcs_context_and_catalog_in_one_read() -> None:
    repository = FakeRepository(
        _state(
            workspace_scope=_scope(
                "workspace",
                WORKSPACE_ID,
                mode="shadow",
            )
        )
    )
    group_facade = FakeGroupFacade(_context(owner="owner"))

    source = _facade(repository, group_facade).resolve_admission_source(
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=GROUP_ID,
        observed_topology_revision=7,
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
        allowed_group_ids=[GROUP_ID],
    )

    assert source.snapshot.workspace_id == WORKSPACE_ID
    assert source.active_group_context.group_id == GROUP_ID
    assert source.catalog_products[0]["pcs_id"] == (
        "instagram_workspace_intelligence"
    )
    assert repository.effective_reads == 1
    assert group_facade.calls == 1


def test_first_workspace_save_is_configuration_only_and_returns_wpcs() -> None:
    repository = FakeRepository(_state())
    artifact = _artifact()

    snapshot = _facade(repository).replace_scope(
        scope_kind="workspace",
        scope_id=WORKSPACE_ID,
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=None,
        observed_topology_revision=None,
        command=ReplaceScopeCommand(
            expected_revision=0,
            catalog_hash=artifact["catalog_hash"],
            assignments=[
                {
                    "pcs_id": "instagram_workspace_intelligence",
                    "pcs_version": "1.0.0",
                }
            ],
        ),
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
    )

    assert snapshot.workspace_admission_mode == "configuration_only"
    assert snapshot.workspace_scope_revision == 1
    assert snapshot.effective_assignments[0].host_ready is True
    assert repository.writes[0]["admission_mode"] == "configuration_only"
    assert repository.effective_reads == 1


def test_group_and_workspace_sources_remain_visible_without_unioning_groups() -> None:
    repository = FakeRepository(
        _state(
            workspace_scope=_scope(
                "workspace",
                WORKSPACE_ID,
                mode="shadow",
            ),
            group_scope=_scope("workspace_group", GROUP_ID),
        )
    )
    snapshot = _facade(
        repository,
        FakeGroupFacade(_context(owner="owner")),
    ).resolve_snapshot(
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=GROUP_ID,
        observed_topology_revision=7,
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
        allowed_group_ids=[GROUP_ID],
    )

    assert snapshot.explicit_active_group_id == GROUP_ID
    assert snapshot.editable_scopes == ["workspace", "workspace_group"]
    assert snapshot.effective_assignments[0].configuration_sources == [
        "workspace",
        "workspace_group",
    ]


def test_host_requirement_without_binding_makes_legacy_host_ready_false() -> None:
    artifact = _artifact_with_host_requirement()
    scope = _scope("workspace", WORKSPACE_ID, mode="enforced")
    scope["catalog_hash"] = artifact["catalog_hash"]
    state = {
        "artifact_hash": artifact["artifact_hash"],
        "catalog_hash": artifact["catalog_hash"],
        "source_commit": artifact["source_commit"],
        "compiler_version": artifact["compiler_version"],
        "artifact": artifact,
        "readiness": {"ig": {"enabled": True, "version": "1.0.195"}},
        "host_readiness": [],
        "scopes": [scope],
    }

    assignment = _facade(FakeRepository(state)).resolve_snapshot(
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=None,
        observed_topology_revision=None,
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
    ).effective_assignments[0]

    assert assignment.host_ready is False
    assert assignment.host_admission[0].blockers == [
        "binding_missing",
        "grant_missing",
    ]


def test_host_requirement_uses_same_read_composite_grant_and_attestation() -> None:
    artifact = _artifact_with_host_requirement()
    scope = _scope("workspace", WORKSPACE_ID, mode="enforced")
    scope["catalog_hash"] = artifact["catalog_hash"]
    now = datetime.now(timezone.utc)
    conditions = [
        {
            "type": condition_type,
            "status": "true",
            "reason": "verified",
            "observed_generation": 2,
            "observed_at": now.isoformat(),
        }
        for condition_type in (
            "Materialized",
            "RuntimeDigestVerified",
            "SupervisorReady",
            "PermissionsReady",
            "ResourceLaneReady",
        )
    ]
    state = {
        "artifact_hash": artifact["artifact_hash"],
        "catalog_hash": artifact["catalog_hash"],
        "source_commit": artifact["source_commit"],
        "compiler_version": artifact["compiler_version"],
        "artifact": artifact,
        "readiness": {"ig": {"enabled": True, "version": "1.0.195"}},
        "host_readiness": [
            {
                "pack_code": "ig",
                "requirement_code": "ig_host_automation",
                "operation": "watch-screenshots",
                "binding": {
                    "id": "binding-a",
                    "device_id": "device-a",
                    "capability_code": "ig",
                    "requirement_code": "ig_host_automation",
                    "capability_version": "1.0.195",
                    "runtime_digest": "a" * 64,
                    "host_assets_digest": "a" * 64,
                    "entrypoint": "scripts/host_runtime_entry.py",
                    "entrypoint_digest": "d" * 64,
                    "desired_state": "active",
                    "generation": 2,
                    "share_policy": "workspace_grants",
                    "operations": ["watch-screenshots"],
                    "permission_classes": ["filesystem.read"],
                    "resource_lane": "host.io.light",
                    "materialized_root": "/runtime/ig",
                    "finalizers": ["mindscape.ai/host-runtime-cleanup"],
                },
                "attestation": {
                    "revision": 4,
                    "observed_generation": 2,
                    "runtime_digest": "a" * 64,
                    "executor_identity_digest": "c" * 64,
                    "permission_revision": 3,
                    "conditions": conditions,
                    "observed_at": now.isoformat(),
                },
                "grant": {
                    "id": "grant-a",
                    "workspace_id": WORKSPACE_ID,
                    "binding_id": "binding-a",
                    "binding_generation": 2,
                    "operation": "watch-screenshots",
                    "operation_args_sha256": "d" * 64,
                    "policy_revision": 3,
                    "attestation_revision": 4,
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "status": "active",
                    "provider_code": None,
                    "voice_profile_id": None,
                    "reference_rights_revision": None,
                },
            }
        ],
        "scopes": [scope],
    }

    assignment = _facade(FakeRepository(state)).resolve_snapshot(
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=None,
        observed_topology_revision=None,
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
    ).effective_assignments[0]

    assert assignment.host_ready is True
    assert assignment.host_admission[0].admitted is True
    assert assignment.host_admission[0].attestation_revision == 4
    assert assignment.host_admission[0].policy_revision == 3


def test_workspace_and_group_version_conflict_fails_closed() -> None:
    artifact = _artifact()
    second_version = deepcopy(artifact["catalog"]["products"][0])
    second_version["version"] = "2.0.0"
    artifact["catalog"]["products"].append(second_version)
    artifact["catalog_hash"] = sha256(_canonical(artifact["catalog"])).hexdigest()
    unsigned = {
        key: value for key, value in artifact.items() if key != "artifact_hash"
    }
    artifact["artifact_hash"] = sha256(_canonical(unsigned)).hexdigest()
    workspace_scope = _scope("workspace", WORKSPACE_ID, mode="shadow")
    group_scope = _scope("workspace_group", GROUP_ID)
    workspace_scope["catalog_hash"] = artifact["catalog_hash"]
    group_scope["catalog_hash"] = artifact["catalog_hash"]
    group_scope["assignments"][0]["pcs_version"] = "2.0.0"
    state = {
        "artifact_hash": artifact["artifact_hash"],
        "catalog_hash": artifact["catalog_hash"],
        "source_commit": artifact["source_commit"],
        "compiler_version": artifact["compiler_version"],
        "artifact": artifact,
        "readiness": {"ig": {"enabled": True, "version": "1.0.195"}},
        "scopes": [workspace_scope, group_scope],
    }

    snapshot = _facade(
        FakeRepository(state),
        FakeGroupFacade(_context(owner="owner")),
    ).resolve_snapshot(
        workspace_id=WORKSPACE_ID,
        explicit_active_group_id=GROUP_ID,
        observed_topology_revision=7,
        actor_user_id="owner",
        allowed_workspace_ids=[WORKSPACE_ID],
        allowed_group_ids=[GROUP_ID],
    )

    assert snapshot.effective_assignments == []
    assert snapshot.configuration_errors == [
        "assignment_version_conflict:"
        "instagram_workspace_intelligence:1.0.0,2.0.0"
    ]


def test_group_scope_cannot_change_member_admission_mode() -> None:
    repository = FakeRepository(
        _state(group_scope=_scope("workspace_group", GROUP_ID))
    )
    artifact = _artifact()
    with pytest.raises(
        WorkspaceProductConfigurationError,
        match="group_scope_cannot_set_admission_mode",
    ):
        _facade(
            repository,
            FakeGroupFacade(_context(owner="owner")),
        ).replace_scope(
            scope_kind="workspace_group",
            scope_id=GROUP_ID,
            workspace_id=WORKSPACE_ID,
            explicit_active_group_id=GROUP_ID,
            observed_topology_revision=7,
            command=ReplaceScopeCommand(
                expected_revision=1,
                catalog_hash=artifact["catalog_hash"],
                admission_mode="enforced",
                assignments=[],
            ),
            actor_user_id="owner",
            allowed_workspace_ids=[WORKSPACE_ID],
            allowed_group_ids=[GROUP_ID],
        )


def test_group_mutation_requires_observed_topology_revision() -> None:
    artifact = _artifact()
    with pytest.raises(TopologyRevisionRequiredError):
        _facade(
            FakeRepository(_state()),
            FakeGroupFacade(_context(owner="owner")),
        ).replace_scope(
            scope_kind="workspace_group",
            scope_id=GROUP_ID,
            workspace_id=WORKSPACE_ID,
            explicit_active_group_id=GROUP_ID,
            observed_topology_revision=None,
            command=ReplaceScopeCommand(
                expected_revision=0,
                catalog_hash=artifact["catalog_hash"],
                assignments=[],
            ),
            actor_user_id="owner",
            allowed_workspace_ids=[WORKSPACE_ID],
            allowed_group_ids=[GROUP_ID],
        )


def test_observed_topology_revision_is_cas_guard() -> None:
    with pytest.raises(TopologyRevisionConflictError):
        _facade(
            FakeRepository(_state()),
            FakeGroupFacade(_context()),
        ).resolve_snapshot(
            workspace_id=WORKSPACE_ID,
            explicit_active_group_id=GROUP_ID,
            observed_topology_revision=6,
            actor_user_id="owner",
            allowed_workspace_ids=[WORKSPACE_ID],
            allowed_group_ids=[GROUP_ID],
        )


def test_catalog_artifact_rejects_semantic_tamper() -> None:
    artifact = _artifact()
    artifact["catalog"]["products"][0]["display_name"] = "tampered"
    with pytest.raises(CatalogArtifactInvalidError, match="catalog_hash_mismatch"):
        verify_catalog_artifact(artifact)


def test_catalog_artifact_enforces_product_count_limit() -> None:
    artifact = _artifact()
    product = artifact["catalog"]["products"][0]
    artifact["catalog"]["products"] = []
    for index in range(65):
        candidate = deepcopy(product)
        candidate["pcs_id"] = f"product_{index:02d}"
        candidate["product_surfaces"][0]["id"] = f"surface.product_{index:02d}"
        artifact["catalog"]["products"].append(candidate)
    artifact["catalog_hash"] = sha256(_canonical(artifact["catalog"])).hexdigest()
    unsigned = {
        key: value for key, value in artifact.items() if key != "artifact_hash"
    }
    artifact["artifact_hash"] = sha256(_canonical(unsigned)).hexdigest()

    with pytest.raises(
        CatalogArtifactInvalidError,
        match="artifact_product_limit_exceeded",
    ):
        verify_catalog_artifact(artifact)


def test_effective_snapshot_fails_closed_above_64_kib() -> None:
    artifact = _artifact()
    product = artifact["catalog"]["products"][0]
    artifact["catalog"]["products"] = []
    for index in range(64):
        candidate = deepcopy(product)
        candidate["pcs_id"] = f"product_{index:02d}"
        candidate["display_name"] = "Product " + ("x" * 100)
        candidate["outcome_summary"] = "y" * 500
        candidate["product_surfaces"] = [
            {
                "id": f"surface.product_{index:02d}.{surface_index:02d}."
                + ("z" * 60),
                "display_name": "Surface",
                "selectors": {"api_prefixes": ["/api/v1/test"]},
            }
            for surface_index in range(16)
        ]
        artifact["catalog"]["products"].append(candidate)
    artifact["catalog_hash"] = sha256(_canonical(artifact["catalog"])).hexdigest()
    unsigned = {
        key: value for key, value in artifact.items() if key != "artifact_hash"
    }
    artifact["artifact_hash"] = sha256(_canonical(unsigned)).hexdigest()
    state = {
        "artifact_hash": artifact["artifact_hash"],
        "catalog_hash": artifact["catalog_hash"],
        "source_commit": artifact["source_commit"],
        "compiler_version": artifact["compiler_version"],
        "artifact": artifact,
        "readiness": {"ig": {"enabled": True, "version": "1.0.195"}},
        "scopes": [],
    }

    with pytest.raises(WorkspaceProductSnapshotLimitError):
        _facade(FakeRepository(state)).resolve_snapshot(
            workspace_id=WORKSPACE_ID,
            explicit_active_group_id=None,
            observed_topology_revision=None,
            actor_user_id="owner",
            allowed_workspace_ids=[WORKSPACE_ID],
        )


def test_catalog_import_delegates_only_after_verification() -> None:
    repository = FakeRepository(_state())
    result = _facade(repository).import_catalog(
        _artifact(),
        actor_user_id="operator",
    )

    assert result.imported is True
    assert len(repository.imports) == 1
