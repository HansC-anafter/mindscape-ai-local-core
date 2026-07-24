import pytest

from backend.app.models.workspace_resource_binding import (
    AccessMode,
    CreateWorkspaceResourceBindingRequest,
    ResourceType,
    UpdateWorkspaceResourceBindingRequest,
    WorkspaceResourceBinding,
)
from backend.app.services.workspace_resource_bindings import (
    WorkspaceResourceBindingConflictError,
    WorkspaceResourceBindingFacade,
    WorkspaceResourceBindingNotFoundError,
    WorkspaceResourceBindingWorkspaceMismatchError,
)


class FakeBindingStore:
    def __init__(self):
        self.bindings: dict[tuple[str, ResourceType, str], WorkspaceResourceBinding] = {}

    def get_binding_by_resource(self, *, workspace_id, resource_type, resource_id):
        return self.bindings.get((workspace_id, resource_type, resource_id))

    def save_binding(self, binding):
        self.bindings[
            (binding.workspace_id, binding.resource_type, binding.resource_id)
        ] = binding
        return binding

    def list_bindings_by_workspace(self, *, workspace_id, resource_type=None):
        return [
            binding
            for binding in self.bindings.values()
            if binding.workspace_id == workspace_id
            and (resource_type is None or binding.resource_type == resource_type)
        ]

    def list_bindings_by_resource(self, *, resource_type, resource_id):
        return [
            binding
            for binding in self.bindings.values()
            if binding.resource_type == resource_type
            and binding.resource_id == resource_id
        ]

    def delete_binding_by_resource(self, *, workspace_id, resource_type, resource_id):
        return self.bindings.pop((workspace_id, resource_type, resource_id), None) is not None


def _request(workspace_id="workspace-1"):
    return CreateWorkspaceResourceBindingRequest(
        workspace_id=workspace_id,
        resource_type=ResourceType.ASSET,
        resource_id="ig-seed:sinnie_withu",
        access_mode=AccessMode.READ,
        overrides={"group_id": "group-1"},
    )


def test_facade_preserves_create_get_update_list_delete_contract():
    facade = WorkspaceResourceBindingFacade(FakeBindingStore())

    created = facade.create(workspace_id="workspace-1", request=_request())
    assert created.workspace_id == "workspace-1"
    assert facade.get(
        workspace_id="workspace-1",
        resource_type=ResourceType.ASSET,
        resource_id="ig-seed:sinnie_withu",
    ).id == created.id
    assert facade.list_for_workspace(workspace_id="workspace-1") == [created]
    assert facade.list_workspaces_using_resource(
        resource_type=ResourceType.ASSET,
        resource_id="ig-seed:sinnie_withu",
    ) == [created]

    updated = facade.update(
        workspace_id="workspace-1",
        resource_type=ResourceType.ASSET,
        resource_id="ig-seed:sinnie_withu",
        request=UpdateWorkspaceResourceBindingRequest(
            overrides={"group_id": "group-2"}
        ),
    )
    assert updated.overrides == {"group_id": "group-2"}

    facade.delete(
        workspace_id="workspace-1",
        resource_type=ResourceType.ASSET,
        resource_id="ig-seed:sinnie_withu",
    )
    with pytest.raises(WorkspaceResourceBindingNotFoundError):
        facade.get(
            workspace_id="workspace-1",
            resource_type=ResourceType.ASSET,
            resource_id="ig-seed:sinnie_withu",
        )


def test_facade_rejects_workspace_mismatch_and_duplicate_binding():
    facade = WorkspaceResourceBindingFacade(FakeBindingStore())
    with pytest.raises(WorkspaceResourceBindingWorkspaceMismatchError):
        facade.create(workspace_id="workspace-2", request=_request("workspace-1"))

    facade.create(workspace_id="workspace-1", request=_request())
    with pytest.raises(WorkspaceResourceBindingConflictError) as exc_info:
        facade.create(workspace_id="workspace-1", request=_request())
    assert str(exc_info.value) == (
        "Binding already exists for ResourceType.ASSET:ig-seed:sinnie_withu"
    )
