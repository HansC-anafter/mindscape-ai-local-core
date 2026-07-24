"""Register the Workspace Product Configuration facade routes."""

from fastapi import FastAPI


def register_workspace_product_routes(app: FastAPI) -> None:
    from backend.app.routes.core.workspace_product_configuration import router

    app.include_router(router)
