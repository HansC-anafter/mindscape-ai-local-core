from fastapi import FastAPI

from backend.app.routes.core import host_resources


def build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(host_resources.router)
    return app
