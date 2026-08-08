from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from app.app_bootstrap.durable_workflow_routes import (
    register_durable_workflow_routes,
)


def test_gated_route_composition_requires_explicit_dependencies() -> None:
    app = FastAPI()
    service = object()
    read_connection = lambda: None
    register_durable_workflow_routes(
        app,
        review_service=service,
        read_connection=read_connection,
    )
    assert app.state.durable_workflow_review_service is service
    assert app.state.durable_workflow_read_connection is read_connection
    paths = {route.path for route in app.routes}
    assert (
        "/api/v1/workspaces/{workspace_id}/executions/"
        "{execution_id}/durability"
    ) in paths


def test_runtime_composition_remains_unmounted_until_b1() -> None:
    root = Path(__file__).resolve().parents[1]
    routes = (root / "app/app_bootstrap/routes.py").read_text()
    main = (root / "app/main.py").read_text()
    assert "register_" + "durable_workflow_routes" not in routes
    assert "register_" + "durable_workflow_routes" not in main


def test_new_handoff_sources_have_no_pack_dispatch() -> None:
    root = Path(__file__).resolve().parents[1]
    relatives = (
        "app/services/workflow/durable_state/runtime_owner_receipts.py",
        "app/services/workflow/durable_state/release_policy.py",
        "app/services/workspace_capability_admission/durable_workflow_policy.py",
        "app/app_bootstrap/durable_workflow_routes.py",
    )
    forbidden = (
        "capabilities.",
        "provider_pack",
        "pack_id",
        "known_pack",
        "startswith(",
    )
    for relative in relatives:
        source = (root / relative).read_text()
        assert not any(token in source for token in forbidden)
