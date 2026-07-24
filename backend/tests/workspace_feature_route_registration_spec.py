import importlib


def test_workspace_feature_router_imports_event_stream_route():
    module = importlib.import_module("backend.features.workspace.routes")

    paths = {route.path for route in module.router.routes}

    assert "/api/v1/workspaces/{workspace_id}/events/stream" in paths
