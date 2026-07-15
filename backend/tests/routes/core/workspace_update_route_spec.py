import asyncio
from uuid import UUID

from backend.app.models.mindscape import EventType
from backend.app.models.workspace import UpdateWorkspaceRequest, Workspace
from backend.app.routes.core.workspace.crud_core import detail_routes


class FakeWorkspaceStore:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.updated_workspaces = []
        self.events = []

    async def get_workspace(self, workspace_id: str):
        if workspace_id == self.workspace.id:
            return self.workspace
        return None

    async def update_workspace(self, workspace: Workspace):
        self.updated_workspaces.append(workspace)
        return workspace

    def create_event(self, event):
        self.events.append(event)
        return event


def test_update_workspace_persists_fields_and_records_uuid_event(monkeypatch):
    workspace = Workspace(
        id="ws-update",
        title="Workspace",
        description="Before",
        owner_user_id="default-user",
    )
    fake_store = FakeWorkspaceStore(workspace)
    monkeypatch.setattr(detail_routes, "store", fake_store)

    updated = asyncio.run(
        detail_routes.update_workspace(
            "ws-update",
            UpdateWorkspaceRequest(description="After"),
        )
    )

    assert updated.description == "After"
    assert fake_store.updated_workspaces == [workspace]
    assert len(fake_store.events) == 1
    event = fake_store.events[0]
    assert UUID(event.id)
    assert event.event_type == EventType.PROJECT_UPDATED
    assert event.workspace_id == "ws-update"
    assert event.payload == {
        "workspace_id": "ws-update",
        "updated_fields": {"description": "After"},
    }
