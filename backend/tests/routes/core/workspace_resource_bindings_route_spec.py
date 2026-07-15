from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models.workspace_resource_binding import (
    AccessMode,
    ResourceType,
    WorkspaceResourceBinding,
)
from backend.app.routes.core import workspace_resource_bindings as routes
from backend.app.services.workspace_resource_bindings import (
    WorkspaceResourceBindingConflictError,
    WorkspaceResourceBindingNotFoundError,
)


def _binding() -> WorkspaceResourceBinding:
    return WorkspaceResourceBinding(
        id="binding-1",
        workspace_id="workspace-1",
        resource_type=ResourceType.ASSET,
        resource_id="ig-seed:sinnie_withu",
        access_mode=AccessMode.READ,
        overrides={"group_id": "group-1"},
    )


class FakeFacade:
    def __init__(self):
        self.calls = []
        self.error = None

    def _result(self, operation, values, result):
        self.calls.append((operation, values))
        if self.error is not None:
            raise self.error
        return result

    def create(self, **values):
        return self._result("create", values, _binding())

    def list_for_workspace(self, **values):
        return self._result("list_for_workspace", values, [_binding()])

    def get(self, **values):
        return self._result("get", values, _binding())

    def update(self, **values):
        return self._result("update", values, _binding())

    def delete(self, **values):
        return self._result("delete", values, None)

    def list_workspaces_using_resource(self, **values):
        return self._result("list_workspaces_using_resource", values, [_binding()])


def _client(monkeypatch):
    facade = FakeFacade()
    monkeypatch.setattr(routes, "get_binding_facade", lambda: facade)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), facade


def test_resource_binding_routes_delegate_to_canonical_facade(monkeypatch):
    client, facade = _client(monkeypatch)
    response = client.post(
        "/api/v1/workspaces/workspace-1/resource-bindings/",
        json={
            "workspace_id": "workspace-1",
            "resource_type": "asset",
            "resource_id": "ig-seed:sinnie_withu",
            "access_mode": "read",
            "overrides": {"group_id": "group-1"},
        },
    )
    assert response.status_code == 201
    assert response.json()["id"] == "binding-1"
    assert facade.calls[0][0] == "create"

    response = client.get("/api/v1/workspaces/workspace-1/resource-bindings/")
    assert response.status_code == 200
    assert response.json()[0]["resource_id"] == "ig-seed:sinnie_withu"
    assert facade.calls[1][0] == "list_for_workspace"

    item_path = (
        "/api/v1/workspaces/workspace-1/resource-bindings/"
        "asset/ig-seed:sinnie_withu"
    )
    assert client.get(item_path).status_code == 200
    assert client.put(item_path, json={"access_mode": "read"}).status_code == 200
    assert client.delete(item_path).status_code == 204
    by_resource_path = (
        "/api/v1/workspaces/workspace-1/resource-bindings/"
        "by-resource/asset/ig-seed:sinnie_withu"
    )
    assert client.get(by_resource_path).status_code == 200
    assert [call[0] for call in facade.calls] == [
        "create",
        "list_for_workspace",
        "get",
        "update",
        "delete",
        "list_workspaces_using_resource",
    ]


def test_resource_binding_routes_preserve_conflict_and_not_found_status(monkeypatch):
    client, facade = _client(monkeypatch)
    facade.error = WorkspaceResourceBindingConflictError("binding conflict")
    response = client.post(
        "/api/v1/workspaces/workspace-1/resource-bindings/",
        json={
            "workspace_id": "workspace-1",
            "resource_type": "asset",
            "resource_id": "ig-seed:sinnie_withu",
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "binding conflict"}

    facade.error = WorkspaceResourceBindingNotFoundError("binding missing")
    response = client.get(
        "/api/v1/workspaces/workspace-1/resource-bindings/asset/ig-seed:sinnie_withu"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "binding missing"}
