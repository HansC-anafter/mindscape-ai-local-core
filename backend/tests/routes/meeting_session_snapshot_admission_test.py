import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.dependencies.auth import AuthContext
from backend.app.routes import meeting_sessions


def test_meeting_start_rejects_stale_expected_snapshot_before_mutating_session(monkeypatch):
    auth = AuthContext(
        user_id="user-1", tenant_id="local",
        workspace_ids=["workspace-1"], group_ids=["group-1"],
    )
    context = SimpleNamespace(group_id="group-1", revision=4, role="dispatch")
    monkeypatch.setattr(meeting_sessions, "MeetingSessionStore", lambda: SimpleNamespace())
    monkeypatch.setattr(
        meeting_sessions,
        "WorkspaceGroupFacade",
        lambda: SimpleNamespace(resolve_context=lambda **kwargs: context),
    )
    monkeypatch.setattr(
        meeting_sessions,
        "WorkspaceGroupSnapshotService",
        lambda: SimpleNamespace(
            get_or_create=lambda context, actor_user_id: SimpleNamespace(id="snapshot-current")
        ),
    )
    body = meeting_sessions.StartSessionRequest(
        active_group_id="group-1",
        expected_topology_snapshot_id="snapshot-pinned",
    )
    with pytest.raises(HTTPException) as raised:
        asyncio.run(
            meeting_sessions.start_session(
                workspace_id="workspace-1",
                body=body,
                x_group_id=None,
                auth=auth,
            )
        )
    assert raised.value.status_code == 409
    assert raised.value.detail == "workspace_group_snapshot_stale"
