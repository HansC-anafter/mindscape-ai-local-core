"""HTTP facade contract tests without opening database or network resources."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.dependencies.auth import AuthContext
from backend.app.routes.core import knowledge_foundation as routes
from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupMember,
    WorkspaceGroupTopology,
    WorkspaceGroupTopologySnapshot,
)


AUTH = AuthContext(
    user_id="user-1",
    tenant_id="local",
    workspace_ids=["workspace-1"],
    group_ids=["group-1"],
)


def _context(revision: int = 3):
    topology = WorkspaceGroupTopology(
        id="group-1",
        display_name="Learning Group",
        owner_user_id="user-1",
        revision=revision,
        members=[WorkspaceGroupMember(workspace_id="workspace-1", role="dispatch")],
    )
    return ActiveWorkspaceGroupContext(
        group_id="group-1",
        workspace_id="workspace-1",
        role="dispatch",
        revision=revision,
        topology=topology,
    )


def _snapshot(revision: int = 3):
    return WorkspaceGroupTopologySnapshot(
        id="snapshot-1",
        group_id="group-1",
        display_name="Learning Group",
        group_revision=revision,
        content_hash="a" * 64,
        members=[WorkspaceGroupMember(workspace_id="workspace-1", role="dispatch")],
        dispatch_workspace_id="workspace-1",
        created_by_user_id="user-1",
    )


def test_personal_scope_uses_authenticated_actor(monkeypatch):
    command = routes.ScopeAdmissionCommand(workspace_id="workspace-1", mode="personal")
    result = asyncio.run(routes.admit_scope(command, AUTH))
    assert result == {
        "mode": "personal",
        "workspace_id": "workspace-1",
        "actor_user_id": "user-1",
    }


def test_organization_scope_creates_one_immutable_snapshot(monkeypatch):
    group = SimpleNamespace(resolve_context=lambda **kwargs: _context())
    snapshots = SimpleNamespace(get_or_create=lambda context, actor_user_id: _snapshot())
    monkeypatch.setattr(routes, "group_facade", group)
    monkeypatch.setattr(routes, "snapshot_service", snapshots)
    command = routes.ScopeAdmissionCommand(
        workspace_id="workspace-1",
        mode="organization",
        group_id="group-1",
    )
    result = asyncio.run(routes.admit_scope(command, AUTH))
    assert result["actor_user_id"] == "user-1"
    assert result["topology_snapshot"]["id"] == "snapshot-1"
    assert result["topology_snapshot"]["group_revision"] == 3


def test_organization_scope_rejects_stale_snapshot(monkeypatch):
    group = SimpleNamespace(resolve_context=lambda **kwargs: _context(revision=4))
    snapshots = SimpleNamespace(get=lambda snapshot_id: _snapshot(revision=3))
    monkeypatch.setattr(routes, "group_facade", group)
    monkeypatch.setattr(routes, "snapshot_service", snapshots)
    command = routes.ScopeAdmissionCommand(
        workspace_id="workspace-1",
        mode="organization",
        group_id="group-1",
        topology_snapshot_id="snapshot-1",
    )
    with pytest.raises(HTTPException) as raised:
        asyncio.run(routes.admit_scope(command, AUTH))
    assert raised.value.status_code == 409
    assert "stale" in str(raised.value.detail)


def test_group_packet_forwards_authenticated_scope(monkeypatch):
    calls = []

    class Knowledge:
        def compile_group_packet(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(model_dump=lambda mode: {
                "topology_snapshot_id": kwargs["topology_snapshot_id"],
                "entries": [],
            })

    monkeypatch.setattr(routes, "knowledge_facade", Knowledge())
    result = asyncio.run(
        routes.compile_group_packet(
            topology_snapshot_id="snapshot-1",
            requesting_workspace_id="workspace-1",
            agent_role="teacher",
            limit=50,
            auth=AUTH,
        )
    )
    assert result["topology_snapshot_id"] == "snapshot-1"
    assert calls[0]["actor_user_id"] == "user-1"
    assert calls[0]["allowed_group_ids"] == ["group-1"]
