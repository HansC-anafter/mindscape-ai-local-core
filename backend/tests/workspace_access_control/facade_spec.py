from hashlib import sha256

from backend.app.services.workspace_access_control.catalog import (
    WORKSPACE_EXECUTE,
    WORKSPACE_MEMBERS_MANAGE,
    WORKSPACE_READ,
)
from backend.app.services.workspace_access_control.contracts import (
    InvitationCreateCommand,
    VerifiedIdentity,
)
from backend.app.services.workspace_access_control.facade import (
    WorkspaceAccessControlFacade,
)


class FakeRepository:
    def __init__(self):
        self.invitation = None
        self.imports = []

    def resolve_effective_access(self, **_kwargs):
        return {
            "principal_id": "principal-1",
            "roles": ["workspace_editor", "local_core_super_admin"],
            "scope_revision": 7,
        }

    def create_invitation(self, **kwargs):
        self.invitation = kwargs
        return 2

    def import_verified_grant(self, **kwargs):
        self.imports.append(kwargs)
        return True

    def read_scope_projection(self, **_kwargs):
        return {
            "revision": 3,
            "members": [{"principal_id": "principal-1"}],
            "invitations": [],
            "audit_events": [],
        }


def test_effective_permissions_union_roles_without_exposing_role_checks():
    facade = WorkspaceAccessControlFacade(repository=FakeRepository())
    context = facade.resolve_effective_access(
        identity=VerifiedIdentity(
            provider="cloudflare-access",
            issuer="https://example.cloudflareaccess.com",
            subject="subject-a",
        ),
        workspace_id="workspace-a",
    )
    assert context.allows(WORKSPACE_READ)
    assert context.allows(WORKSPACE_EXECUTE)
    assert context.allows(WORKSPACE_MEMBERS_MANAGE)
    assert context.scope_revision == 7


def test_invitation_raw_token_is_never_passed_to_repository():
    repository = FakeRepository()
    facade = WorkspaceAccessControlFacade(repository=repository)
    created = facade.create_invitation(
        command=InvitationCreateCommand(
            scope_type="workspace",
            scope_id="workspace-a",
            email="USER@example.com",
            role_key="workspace_editor",
            expected_revision=1,
        ),
        actor_principal_id="owner-1",
    )
    assert created.email == "user@example.com"
    assert repository.invitation["token_hash"] == sha256(
        created.invitation_token.encode("utf-8")
    ).hexdigest()
    assert created.invitation_token not in repr(repository.invitation)


def test_cloud_import_uses_stable_identity_and_grant_keys():
    repository = FakeRepository()
    facade = WorkspaceAccessControlFacade(repository=repository)
    identity = VerifiedIdentity(
        provider="cloudflare-access",
        issuer="https://example.cloudflareaccess.com",
        subject="subject-a",
        verified_email="user@example.com",
    )
    assert facade.import_verified_grant(
        identity=identity,
        scope_type="workspace",
        scope_id="workspace-a",
        role_key="workspace_editor",
        actor_id="importer",
    )
    assert facade.import_verified_grant(
        identity=identity,
        scope_type="workspace",
        scope_id="workspace-a",
        role_key="workspace_editor",
        actor_id="importer",
    )
    assert repository.imports[0]["principal_id"] == repository.imports[1]["principal_id"]
    assert repository.imports[0]["grant_id"] == repository.imports[1]["grant_id"]


def test_scope_projection_returns_the_bounded_facade_contract():
    facade = WorkspaceAccessControlFacade(repository=FakeRepository())
    projection = facade.read_scope(
        scope_type="workspace",
        scope_id="workspace-a",
        limit=64,
    )
    assert projection.scope_id == "workspace-a"
    assert projection.revision == 3
    assert projection.members == [{"principal_id": "principal-1"}]
