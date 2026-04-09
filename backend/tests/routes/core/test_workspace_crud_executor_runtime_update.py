import asyncio
from types import SimpleNamespace

from backend.app.models.workspace import UpdateWorkspaceRequest, Workspace
from backend.app.routes.core.workspace import crud as module


class _FakeStore:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.updated_workspace = None
        self.events = []

    async def get_workspace(self, workspace_id: str):
        if workspace_id == self.workspace.id:
            return self.workspace
        return None

    async def update_workspace(self, workspace: Workspace):
        self.updated_workspace = workspace
        self.workspace = workspace
        return workspace

    def create_event(self, event):
        self.events.append(event)
        return event


def _make_workspace() -> Workspace:
    return Workspace(
        id="ws-update-001",
        title="Runtime Update Workspace",
        owner_user_id="user-001",
        executor_runtime=None,
        sandbox_config=None,
        fallback_model=None,
        meeting_enabled=False,
        metadata={},
    )


def test_update_workspace_persists_executor_runtime_related_fields(monkeypatch):
    workspace = _make_workspace()
    fake_store = _FakeStore(workspace)

    monkeypatch.setattr(module, "store", fake_store)
    monkeypatch.setattr(
        module,
        "StoragePathValidator",
        SimpleNamespace(
            validate_and_check_host_path=lambda path: (True, None, None),
            get_allowed_directories=lambda: [],
            validate_path_in_allowed_directories=lambda path, allowed: True,
        ),
    )

    request = UpdateWorkspaceRequest(
        executor_runtime="codex_cli",
        meeting_enabled=True,
        sandbox_config={"tool_policies": {"network": "restricted"}},
        fallback_model="qwen3:8b",
    )

    updated = asyncio.run(module.update_workspace("ws-update-001", request))

    assert updated.executor_runtime == "codex_cli"
    assert updated.meeting_enabled is True
    assert updated.sandbox_config == {"tool_policies": {"network": "restricted"}}
    assert updated.fallback_model == "qwen3:8b"
    assert fake_store.updated_workspace is updated
