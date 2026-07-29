from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.dependencies.auth import AuthContext
from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalAccessContextFactory,
    RetrievalScopeDenied,
)
from backend.app.services.knowledge_authorization.workspace_authorization_revision import (
    workspace_authorization_revision,
)


def _workspace(
    *,
    updated_at: datetime,
    owner_user_id: str = "user-1",
    visibility: str = "private",
) -> SimpleNamespace:
    return SimpleNamespace(
        id="workspace-1",
        owner_user_id=owner_user_id,
        visibility=visibility,
        updated_at=updated_at,
    )


def _context(workspace: SimpleNamespace):
    return RetrievalAccessContextFactory(
        workspace_lookup=lambda _workspace_id: workspace,
        group_lookup=lambda _group_id: None,
    ).build(
        AuthContext(user_id="user-1", tenant_id="local"),
        requested_workspace_ids=["workspace-1"],
    )


def test_unrelated_workspace_updates_do_not_invalidate_authorization_context():
    first = _context(
        _workspace(
            updated_at=datetime(2026, 7, 27, tzinfo=timezone.utc),
        )
    )
    later = _context(
        _workspace(
            updated_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        )
    )

    assert first.memberships[0].revision == later.memberships[0].revision
    assert first.principal_set_hash == later.principal_set_hash


def test_authority_fields_change_the_workspace_revision():
    baseline = workspace_authorization_revision(
        workspace_id="workspace-1",
        owner_user_id="user-1",
        visibility="private",
    )
    owner_changed = workspace_authorization_revision(
        workspace_id="workspace-1",
        owner_user_id="user-2",
        visibility="private",
    )
    visibility_changed = workspace_authorization_revision(
        workspace_id="workspace-1",
        owner_user_id="user-1",
        visibility="group",
    )

    assert baseline != owner_changed
    assert baseline != visibility_changed


def test_missing_visibility_fails_closed():
    with pytest.raises(RetrievalScopeDenied) as error:
        _context(
            _workspace(
                updated_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
                visibility="",
            )
        )

    assert (
        error.value.code
        == "knowledge_workspace_authorization_visibility_missing"
    )
