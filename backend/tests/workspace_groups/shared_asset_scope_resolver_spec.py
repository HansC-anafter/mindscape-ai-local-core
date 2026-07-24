from dataclasses import replace

import pytest

from backend.app.services.workspace_groups.contracts import SharedAssetScopeResolution
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.shared_asset_scope_repository import (
    SharedAssetScopeEvidence,
)
from backend.app.services.workspace_groups.shared_asset_scope_resolver import (
    SharedAssetScopeAccessError,
    SharedAssetScopeResolver,
    SharedAssetScopeWorkspaceNotFoundError,
)


def _overrides(*, group_id="group-1", source_workspace_id="source", selector=None):
    return {
        "group_id": group_id,
        "source_workspace_id": source_workspace_id,
        "share_scope": "workspace_group",
        "dynamic_selector": selector
        or {
            "reference_seed": "sinnie_withu",
            "following_seed": "sinnie_withu",
            "include_future_matches": True,
        },
    }


def _evidence(**changes):
    base = SharedAssetScopeEvidence(
        binding_id="binding-1",
        active_workspace_id="consumer",
        active_workspace_owner_user_id="owner",
        consumer_access_mode="read",
        consumer_overrides=_overrides(),
        resource_id="ig-seed:sinnie_withu",
        source_binding_id="source-binding",
        source_workspace_id="source",
        source_workspace_title="Source Workspace",
        source_access_mode="read",
        source_overrides=_overrides(),
        group_id="group-1",
        group_title="Group 1",
        group_owner_user_id="owner",
        group_revision=3,
        consumer_is_member=True,
        source_is_member=True,
        topology_is_ready=True,
    )
    return replace(base, **changes)


class FakeRepository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_evidence(self, *, workspace_id, group_id=None):
        self.calls.append((workspace_id, group_id))
        return self.rows


def test_resolver_returns_typed_authorized_scope_and_stable_fingerprint():
    repository = FakeRepository([_evidence()])
    resolver = SharedAssetScopeResolver(repository)

    result = resolver.resolve(
        workspace_id="consumer",
        actor_user_id="owner",
    )

    assert repository.calls == [("consumer", None)]
    assert len(result.scopes) == 1
    assert result.errors == []
    scope = result.scopes[0]
    assert scope.origin == "workspace_group_shared"
    assert scope.source_workspace_id == "source"
    assert scope.selector.reference_seed == "sinnie_withu"
    assert scope.scope_key.startswith("wgs_")
    assert len(result.scope_fingerprint) == 64

    same = resolver.resolve(workspace_id="consumer", actor_user_id="owner")
    assert same.scope_fingerprint == result.scope_fingerprint

    revised = SharedAssetScopeResolver(
        FakeRepository([_evidence(group_revision=4)])
    ).resolve(workspace_id="consumer", actor_user_id="owner")
    assert revised.scope_fingerprint != result.scope_fingerprint


def test_resolver_returns_every_valid_scope_without_first_group_fallback():
    group_two = _evidence(
        binding_id="binding-2",
        group_id="group-2",
        group_title="Group 2",
        consumer_overrides=_overrides(group_id="group-2"),
        source_overrides=_overrides(group_id="group-2"),
    )
    repository = FakeRepository([group_two, _evidence()])
    result = SharedAssetScopeResolver(repository).resolve(
        workspace_id="consumer",
        actor_user_id="owner",
    )

    assert [scope.group_id for scope in result.scopes] == ["group-1", "group-2"]
    assert repository.calls == [("consumer", None)]


def test_resolver_forwards_explicit_group_filter_without_fallback():
    repository = FakeRepository(
        [
            _evidence(
                binding_id=None,
                consumer_access_mode=None,
                consumer_overrides={},
                resource_id=None,
                source_binding_id=None,
                source_workspace_id=None,
                source_workspace_title=None,
                source_access_mode=None,
                source_overrides={},
                group_id=None,
                group_title=None,
                group_owner_user_id=None,
                group_revision=None,
                consumer_is_member=False,
                source_is_member=False,
                topology_is_ready=False,
            )
        ]
    )
    result = SharedAssetScopeResolver(repository).resolve(
        workspace_id="consumer",
        actor_user_id="owner",
        group_id="group-missing",
    )
    assert repository.calls == [("consumer", "group-missing")]
    assert result.scopes == []


def test_resolver_fails_closed_per_invalid_scope_without_hiding_valid_scope():
    invalid = _evidence(
        binding_id="binding-invalid",
        source_binding_id=None,
        source_workspace_id=None,
        source_workspace_title=None,
        source_access_mode=None,
        source_overrides={},
        source_is_member=False,
    )
    result = SharedAssetScopeResolver(FakeRepository([invalid, _evidence()])).resolve(
        workspace_id="consumer",
        actor_user_id="owner",
    )

    assert len(result.scopes) == 1
    assert [error.code for error in result.errors] == [
        "shared_scope_source_binding_missing"
    ]


def test_resolver_requires_workspace_group_and_source_anchor_authorization():
    resolver = SharedAssetScopeResolver(FakeRepository([_evidence()]))
    with pytest.raises(SharedAssetScopeAccessError):
        resolver.resolve(
            workspace_id="consumer",
            actor_user_id="outside",
        )

    workspace_member = resolver.resolve(
        workspace_id="consumer",
        actor_user_id="outside",
        allowed_workspace_ids=["consumer"],
    )
    assert workspace_member.errors[0].code == "shared_scope_group_access_denied"

    authorized = resolver.resolve(
        workspace_id="consumer",
        actor_user_id="outside",
        allowed_workspace_ids=["consumer"],
        allowed_group_ids=["group-1"],
    )
    assert len(authorized.scopes) == 1


def test_resolver_distinguishes_missing_workspace_from_no_shared_bindings():
    with pytest.raises(SharedAssetScopeWorkspaceNotFoundError):
        SharedAssetScopeResolver(FakeRepository([])).resolve(
            workspace_id="missing",
            actor_user_id="owner",
        )

    empty_binding_row = _evidence(
        binding_id=None,
        consumer_access_mode=None,
        consumer_overrides={},
        resource_id=None,
        source_binding_id=None,
        source_workspace_id=None,
        source_workspace_title=None,
        source_access_mode=None,
        source_overrides={},
        group_id=None,
        group_title=None,
        group_owner_user_id=None,
        group_revision=None,
        consumer_is_member=False,
        source_is_member=False,
        topology_is_ready=False,
    )
    result = SharedAssetScopeResolver(FakeRepository([empty_binding_row])).resolve(
        workspace_id="consumer",
        actor_user_id="owner",
    )
    assert result.scopes == []
    assert result.errors == []


def test_resolver_rejects_malformed_or_mismatched_selectors():
    malformed = _evidence(
        consumer_overrides=_overrides(selector={"reference_seed": "only-one"})
    )
    mismatched = _evidence(
        binding_id="binding-2",
        source_overrides=_overrides(
            selector={
                "reference_seed": "other",
                "following_seed": "other",
                "include_future_matches": True,
            }
        ),
    )
    result = SharedAssetScopeResolver(
        FakeRepository([malformed, mismatched])
    ).resolve(workspace_id="consumer", actor_user_id="owner")
    assert [error.code for error in result.errors] == [
        "shared_scope_selector_invalid",
        "shared_scope_selector_mismatch",
    ]


def test_resolver_bounds_invalid_scope_errors_to_twenty():
    rows = [
        _evidence(binding_id=f"binding-{index}", topology_is_ready=False)
        for index in range(25)
    ]
    result = SharedAssetScopeResolver(FakeRepository(rows)).resolve(
        workspace_id="consumer",
        actor_user_id="owner",
    )
    assert len(result.errors) == 20
    assert all(error.code == "shared_scope_topology_invalid" for error in result.errors)


def test_workspace_group_facade_is_the_only_shared_scope_entrypoint():
    expected = SharedAssetScopeResolution(
        scopes=[],
        errors=[],
        scope_fingerprint="f" * 64,
    )

    class CapturingResolver:
        def __init__(self):
            self.values = None

        def resolve(self, **values):
            self.values = values
            return expected

    resolver = CapturingResolver()
    facade = WorkspaceGroupFacade(
        topology_service=object(),
        shared_asset_scope_resolver=resolver,
    )
    result = facade.resolve_shared_asset_scopes(
        workspace_id="consumer",
        actor_user_id="owner",
        allowed_workspace_ids=["consumer"],
        allowed_group_ids=["group-1"],
        group_id="group-1",
    )

    assert result is expected
    assert resolver.values == {
        "workspace_id": "consumer",
        "actor_user_id": "owner",
        "allowed_workspace_ids": ["consumer"],
        "allowed_group_ids": ["group-1"],
        "group_id": "group-1",
    }
