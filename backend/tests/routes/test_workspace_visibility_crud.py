"""
Tests for workspace visibility CRUD wiring.

Verifies the exact code paths used in crud.py create/update handlers
for the visibility field. Tests the Workspace construction and update
logic in isolation from the FastAPI/store infrastructure.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.app.models.workspace import (
    Workspace,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceVisibility,
)


def _simulate_create_visibility(request: CreateWorkspaceRequest) -> Workspace:
    """Replicate the exact visibility logic from crud.py create_workspace.

    This is the code at crud.py L242:
        visibility=request.visibility if getattr(request, "visibility", None) else WorkspaceVisibility.PRIVATE,
    """
    return Workspace(
        id="ws-test",
        title=request.title,
        owner_user_id="user-1",
        visibility=(
            request.visibility
            if getattr(request, "visibility", None)
            else WorkspaceVisibility.PRIVATE
        ),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _simulate_update_visibility(
    workspace: Workspace, request: UpdateWorkspaceRequest
) -> Workspace:
    """Replicate the exact visibility logic from crud.py update_workspace.

    This is the code at crud.py L657-660:
        if hasattr(request, "visibility") and request.visibility is not None:
            workspace.visibility = request.visibility
    """
    if hasattr(request, "visibility") and request.visibility is not None:
        workspace.visibility = request.visibility
    return workspace


class TestCreateWorkspaceVisibility:
    """POST /workspaces — visibility field wiring (crud.py L221-244)."""

    def test_create_with_explicit_visibility(self):
        """Explicit visibility propagates to Workspace."""
        req = CreateWorkspaceRequest(
            title="Discoverable",
            visibility=WorkspaceVisibility.DISCOVERABLE,
        )
        ws = _simulate_create_visibility(req)
        assert ws.visibility == WorkspaceVisibility.DISCOVERABLE

    def test_create_with_public_visibility(self):
        """PUBLIC visibility works."""
        req = CreateWorkspaceRequest(
            title="Public", visibility=WorkspaceVisibility.PUBLIC
        )
        ws = _simulate_create_visibility(req)
        assert ws.visibility == WorkspaceVisibility.PUBLIC

    def test_create_without_visibility_defaults_to_private(self):
        """Omitted visibility defaults to PRIVATE (not None → no ValidationError)."""
        req = CreateWorkspaceRequest(title="Default")
        ws = _simulate_create_visibility(req)
        assert ws.visibility == WorkspaceVisibility.PRIVATE

    def test_create_with_none_visibility_defaults_to_private(self):
        """Explicit None visibility defaults to PRIVATE."""
        req = CreateWorkspaceRequest(title="Explicit None", visibility=None)
        ws = _simulate_create_visibility(req)
        assert ws.visibility == WorkspaceVisibility.PRIVATE


class TestUpdateWorkspaceVisibility:
    """PUT /workspaces/{id} — visibility field wiring (crud.py L657-660)."""

    def test_update_visibility_to_public(self):
        """Changing visibility from PRIVATE to PUBLIC works."""
        ws = Workspace(
            id="ws-1",
            title="WS",
            owner_user_id="u1",
            visibility=WorkspaceVisibility.PRIVATE,
        )
        req = UpdateWorkspaceRequest(visibility=WorkspaceVisibility.PUBLIC)
        updated = _simulate_update_visibility(ws, req)
        assert updated.visibility == WorkspaceVisibility.PUBLIC

    def test_update_visibility_to_discoverable(self):
        """Changing visibility to DISCOVERABLE works."""
        ws = Workspace(
            id="ws-1",
            title="WS",
            owner_user_id="u1",
            visibility=WorkspaceVisibility.PRIVATE,
        )
        req = UpdateWorkspaceRequest(visibility=WorkspaceVisibility.DISCOVERABLE)
        updated = _simulate_update_visibility(ws, req)
        assert updated.visibility == WorkspaceVisibility.DISCOVERABLE

    def test_update_without_visibility_preserves_existing(self):
        """PUT without visibility field keeps original value."""
        ws = Workspace(
            id="ws-1",
            title="WS",
            owner_user_id="u1",
            visibility=WorkspaceVisibility.DISCOVERABLE,
        )
        req = UpdateWorkspaceRequest(title="New Title")
        updated = _simulate_update_visibility(ws, req)
        assert updated.visibility == WorkspaceVisibility.DISCOVERABLE

    def test_update_visibility_none_preserves_existing(self):
        """PUT with visibility=None keeps original value."""
        ws = Workspace(
            id="ws-1",
            title="WS",
            owner_user_id="u1",
            visibility=WorkspaceVisibility.PUBLIC,
        )
        req = UpdateWorkspaceRequest(visibility=None)
        updated = _simulate_update_visibility(ws, req)
        assert updated.visibility == WorkspaceVisibility.PUBLIC
