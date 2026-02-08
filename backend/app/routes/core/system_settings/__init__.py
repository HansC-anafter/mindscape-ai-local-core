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
    governance,
    ports,
    files,
    assistant,
)

router = APIRouter(prefix="/api/v1/system-settings", tags=["system-settings"])

# Register all sub-routers.
# Route registration order matters: register specific routers before the catch-all router to avoid conflicts.
router.include_router(governance.router, prefix="/governance", tags=["governance"])
router.include_router(assistant.router, tags=["assistant"])  # Config assistant chat
router.include_router(llm_models.router)
router.include_router(google_oauth.router)
router.include_router(obsidian.router)
router.include_router(embedding_migrations.router)
router.include_router(env_vars.router)
router.include_router(system_control.router)
router.include_router(ports.router)  # Port configuration routes
router.include_router(files.router)  # File system utility routes
router.include_router(general.router)  # Catch-all routes last
