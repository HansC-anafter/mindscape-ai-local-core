from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

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
    WorkspaceProductConfigurationError,
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
        self.readiness_reads = 0
        self.writes = []
        self.imports = []

    def load_effective_state(self, **kwargs):
        self.effective_reads += 1
        return deepcopy(self.state)

    def load_pack_readiness(self, pack_codes):
        self.readiness_reads += 1
        assert pack_codes == ["ig"]
        return {"ig": {"enabled": True, "version": "1.0.195"}}

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
    assert repository.readiness_reads == 1
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
    assert repository.readiness_reads == 1


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


def test_catalog_import_delegates_only_after_verification() -> None:
    repository = FakeRepository(_state())
    result = _facade(repository).import_catalog(
        _artifact(),
        actor_user_id="operator",
    )

    assert result.imported is True
    assert len(repository.imports) == 1


def test_facade_modules_and_bootstrap_remain_bounded() -> None:
    root = Path(__file__).resolve().parents[3]
    facade = (
        root
        / "backend/app/services/workspace_product_configuration/facade.py"
    )
    bootstrap = root / "backend/app/app_bootstrap/routes.py"
    assert len(facade.read_text(encoding="utf-8").splitlines()) < 500
    assert len(bootstrap.read_text(encoding="utf-8").splitlines()) < 500
