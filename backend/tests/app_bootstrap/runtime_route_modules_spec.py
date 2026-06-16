from pathlib import Path

from fastapi import FastAPI

from backend.app.app_bootstrap.runtime_route_modules import (
    register_runtime_route_modules,
)


def test_runtime_route_modules_register_runtime_dispatch_router():
    app = FastAPI()

    register_runtime_route_modules(app)

    paths = {route.path for route in app.routes}
    assert "/api/v1/runtime-dispatch/selector-types" in paths
    assert "/api/v1/runtime-dispatch/targets" in paths
    assert "/api/v1/runtime-dispatch/preview" in paths
    assert "/api/v1/runtime-dispatch/apply" in paths
    assert "/api/v1/runtime-dispatch/repair" in paths


def test_route_bootstrap_stays_below_large_file_gate():
    route_file = Path("backend/app/app_bootstrap/routes.py")

    assert len(route_file.read_text().splitlines()) <= 500
