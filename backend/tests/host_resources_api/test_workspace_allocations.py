from fastapi.testclient import TestClient

from backend.app.routes.core import host_resources

from .host_resources_api_test_support import build_app


def test_workspace_allocations_endpoint_returns_effective_matrix(monkeypatch):
    class _Store:
        def list_allocations(self, **kwargs):
            assert kwargs["workspace_id"] == "ws-1"
            return [
                {
                    "allocation_id": "alloc-1",
                    "workspace_id": "ws-1",
                    "queue_shard": "default_local_browser",
                    "task_family": "browser_batch",
                    "max_parallel_task_claims": 3,
                }
            ]

    monkeypatch.setattr(
        host_resources,
        "HostResourceWorkspaceAllocationStore",
        lambda scope: _Store(),
    )
    monkeypatch.setattr(
        host_resources,
        "require_workspace_resource_access",
        lambda current_user, workspace_id: workspace_id,
    )
    monkeypatch.setattr(
        host_resources,
        "build_workspace_allocation_effective_matrix",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "effective_matrix": [
                {
                    "queue_shard": "default_local_browser",
                    "task_family": "browser_batch",
                    "max_parallel_task_claims": 3,
                }
            ],
        },
    )

    response = TestClient(build_app()).get(
        "/api/v1/host-resources/workspace-allocations?workspace_id=ws-1"
    )

    assert response.status_code == 200
    assert response.json()["allocations"][0]["task_family"] == "browser_batch"
    assert response.json()["effective"]["effective_matrix"][0][
        "max_parallel_task_claims"
    ] == 3


def test_allocation_blueprint_apply_endpoint_materializes_workspace_quota(monkeypatch):
    received = {}

    def _apply_allocation_blueprint_to_workspace(**kwargs):
        received.update(kwargs)
        return {
            "blueprint": {"blueprint_id": kwargs["blueprint_id"]},
            "application": {"workspace_id": kwargs["workspace_id"]},
            "allocations": [
                {
                    "workspace_id": kwargs["workspace_id"],
                    "queue_shard": "default_local_browser",
                    "task_family": "browser_batch",
                    "max_parallel_task_claims": 3,
                }
            ],
        }

    monkeypatch.setattr(
        host_resources,
        "require_workspace_resource_access",
        lambda current_user, workspace_id: workspace_id,
    )
    monkeypatch.setattr(
        host_resources,
        "apply_allocation_blueprint_to_workspace",
        _apply_allocation_blueprint_to_workspace,
    )
    monkeypatch.setattr(
        host_resources,
        "build_workspace_allocation_effective_matrix",
        lambda workspace_id: {
            "workspace_id": workspace_id,
            "effective_matrix": [{"queue_shard": "default_local_browser"}],
        },
    )

    response = TestClient(build_app()).post(
        "/api/v1/host-resources/allocation-blueprints/"
        "ig-content-production-default/apply",
        json={"workspace_id": "ws-1"},
    )

    assert response.status_code == 200
    assert response.json()["application"]["workspace_id"] == "ws-1"
    assert response.json()["effective"]["effective_matrix"][0][
        "queue_shard"
    ] == "default_local_browser"
    assert received == {
        "workspace_id": "ws-1",
        "blueprint_id": "ig-content-production-default",
        "actor_id": "default_user",
    }
