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
# IMPORTANT: Specific routes (like /llm-models) must be registered BEFORE
# catch-all routes (like /{key}) to avoid route conflicts
router.include_router(llm_models.router)
router.include_router(google_oauth.router)
router.include_router(obsidian.router)
router.include_router(embedding_migrations.router)
router.include_router(env_vars.router)
router.include_router(system_control.router)
router.include_router(general.router)  # Catch-all routes last

