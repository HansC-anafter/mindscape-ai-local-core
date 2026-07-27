from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.dependencies.auth import AuthContext
from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalAccessContextFactory,
    RetrievalScopeDenied,
    VerifiedAgentExecution,
)


def _workspace(workspace_id: str, owner: str = "user-1"):
    return SimpleNamespace(
        id=workspace_id,
        owner_user_id=owner,
        updated_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
    )


def _group(group_id: str, owner: str = "user-1"):
    return SimpleNamespace(
        id=group_id,
        owner_user_id=owner,
        revision=7,
    )


def test_local_owner_roles_use_canonical_owner_rows_only():
    factory = RetrievalAccessContextFactory(
        workspace_lookup=lambda workspace_id: _workspace(workspace_id),
        group_lookup=lambda group_id: _group(group_id),
    )
    context = factory.build(
        AuthContext(
            user_id="user-1",
            tenant_id="local",
            workspace_ids=["workspace-1"],
        ),
        requested_workspace_ids=["workspace-1"],
        requested_group_ids=["group-1"],
        verified_agent_execution=VerifiedAgentExecution(
            role="dispatch",
            policy_revision="policy-7",
            topology_snapshot_id="snapshot-7",
        ),
    )

    assert "user:user-1" in context.principal_keys
    assert "workspace_role:workspace-1:owner" in context.principal_keys
    assert "group_role:group-1:owner" in context.principal_keys
    assert all(item.role not in {"dispatch", "cell"} for item in context.memberships)
    assert context.agent_mask is not None
    assert context.agent_mask.role == "dispatch"
    assert context.has_permission(
        "knowledge.manage_acl",
        scope_type="group",
        scope_id="group-1",
    )


def test_local_non_owner_scope_fails_closed():
    factory = RetrievalAccessContextFactory(
        workspace_lookup=lambda workspace_id: _workspace(workspace_id, "other-user"),
        group_lookup=lambda group_id: None,
    )
    try:
        factory.build(
            AuthContext(user_id="user-1", tenant_id="local"),
            requested_workspace_ids=["workspace-1"],
        )
    except RetrievalScopeDenied as exc:
        assert exc.code == "knowledge_workspace_scope_forbidden"
    else:
        raise AssertionError("non-owner local workspace must fail closed")


def test_cloud_missing_role_revision_keeps_direct_user_but_not_role_principal():
    factory = RetrievalAccessContextFactory(
        workspace_lookup=lambda workspace_id: None,
        group_lookup=lambda group_id: None,
    )
    context = factory.build(
        AuthContext(
            user_id="cloud-user",
            tenant_id="tenant-1",
            workspace_ids=["workspace-1"],
            workspace_memberships=[
                {
                    "scope_type": "workspace",
                    "scope_id": "workspace-1",
                    "role": "editor",
                }
            ],
            is_cloud_mode=True,
        ),
        requested_workspace_ids=["workspace-1"],
    )

    assert context.principal_keys == ("user:cloud-user",)
    assert context.memberships == ()
    assert context.permissions == ()


def test_cloud_scope_and_payload_subject_mismatch_are_rejected():
    factory = RetrievalAccessContextFactory(
        workspace_lookup=lambda workspace_id: None,
        group_lookup=lambda group_id: None,
    )
    auth = AuthContext(
        user_id="cloud-user",
        tenant_id="tenant-1",
        workspace_ids=["workspace-1"],
        is_cloud_mode=True,
    )
    try:
        factory.build(auth, requested_workspace_ids=["workspace-2"])
    except RetrievalScopeDenied as exc:
        assert exc.code == "knowledge_workspace_scope_forbidden"
    else:
        raise AssertionError("unverified cloud workspace must fail closed")
