"""Register the provider-neutral workspace access-control facade routes."""

from fastapi import FastAPI


def register_workspace_access_control_routes(app: FastAPI) -> None:
    from backend.app.routes.core.workspace_access import router

    app.include_router(router)
