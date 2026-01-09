"""
Mindscape Startup Validators

Provides application startup validation mechanism to ensure:
1. No route conflicts
2. No illegal imports
3. All required dependencies are available

Usage:
    from fastapi import FastAPI
    from mindscape.startup import run_startup_validation

    app = FastAPI()

    @app.on_event("startup")
    async def startup():
        if not run_startup_validation(app):
            raise RuntimeError("Startup validation failed")
"""

from .validators import (
    run_startup_validation,
    StartupValidator,
)

__all__ = [
    "run_startup_validation",
    "StartupValidator",
]



