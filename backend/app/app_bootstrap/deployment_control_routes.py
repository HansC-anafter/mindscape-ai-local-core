"""Facade module seam for deployment-control route registration."""

from fastapi import FastAPI


def register_deployment_control_routes(app: FastAPI) -> None:
    from backend.app.routes.core.deployment_control import router

    app.include_router(router)
