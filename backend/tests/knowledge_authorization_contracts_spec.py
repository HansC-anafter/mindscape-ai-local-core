from __future__ import annotations

from backend.app.services.knowledge_authorization.contracts import (
    AgentExecutionMask,
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
    ScopeMembership,
)


def _context(*, reverse: bool = False, role: str = "owner") -> RetrievalAccessContext:
    principals = [
        PrincipalRef("user", "user-1"),
        PrincipalRef("service", "meeting-runtime"),
    ]
    memberships = [
        ScopeMembership("workspace", "workspace-1", role, "revision-1"),
        ScopeMembership("group", "group-1", "member", "revision-2"),
    ]
    permissions = [
        KnowledgePermission("knowledge.read", "workspace", "workspace-1"),
        KnowledgePermission("knowledge.manage_acl", "workspace", "workspace-1"),
    ]
    if reverse:
        principals.reverse()
        memberships.reverse()
        permissions.reverse()
    return RetrievalAccessContext.create(
        subject_user_id="user-1",
        tenant_id="tenant-1",
        principals=principals,
        memberships=memberships,
        permissions=permissions,
        agent_mask=AgentExecutionMask("researcher", "policy-1", "snapshot-1"),
    )


def test_context_hash_is_order_independent_and_includes_role_revision():
    first = _context()
    reordered = _context(reverse=True)
    changed_role = _context(role="editor")

    assert first.principal_set_hash == reordered.principal_set_hash
    assert first.principal_set_hash != changed_role.principal_set_hash
    assert first.principal_keys == tuple(sorted(first.principal_keys))
    assert "workspace_role:workspace-1:owner" in first.principal_keys


def test_context_requires_direct_subject_principal():
    try:
        RetrievalAccessContext.create(
            subject_user_id="user-1",
            tenant_id="tenant-1",
            principals=[PrincipalRef("service", "meeting-runtime")],
        )
    except ValueError as exc:
        assert str(exc) == "knowledge_authorization_subject_principal_required"
    else:
        raise AssertionError("missing subject principal must fail closed")


def test_contract_rejects_generic_admin_and_unknown_principal_types():
    for principal_type in ("admin", "workspace", "agent_role"):
        try:
            PrincipalRef(principal_type, "anything")
        except ValueError as exc:
            assert str(exc) == "knowledge_authorization_principal_type_forbidden"
        else:
            raise AssertionError(f"{principal_type} must not become an ACL principal")

    try:
        KnowledgePermission("admin", "workspace", "workspace-1")
    except ValueError as exc:
        assert str(exc) == "knowledge_authorization_permission_forbidden"
    else:
        raise AssertionError("generic admin bypass must be forbidden")
