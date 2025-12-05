"""
System Settings API Routes

Modular system settings management endpoints.
"""
from fastapi import APIRouter
from . import (
    general,
    obsidian,
    llm_models,
    google_oauth,
    embedding_migrations,
    env_vars,
    system_control,
)

router = APIRouter(prefix="/api/v1/system-settings", tags=["system-settings"])

# Register all sub-routers
router.include_router(general.router)
router.include_router(obsidian.router)
router.include_router(llm_models.router)
router.include_router(google_oauth.router)
router.include_router(embedding_migrations.router)
router.include_router(env_vars.router)
router.include_router(system_control.router)

