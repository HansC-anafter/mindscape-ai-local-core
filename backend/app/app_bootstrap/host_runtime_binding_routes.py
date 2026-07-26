"""Register host runtime binding authority routes."""

from fastapi import FastAPI


def register_host_runtime_binding_routes(app: FastAPI) -> None:
    from backend.app.routes.core.host_runtime_bindings import router

    app.include_router(router)
