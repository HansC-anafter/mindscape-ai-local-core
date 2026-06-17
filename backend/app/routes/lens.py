"""
Lens API routes for Mind-Lens unified implementation.

Provides APIs for:
- Effective Lens resolution
- Workspace Override management
- Session Override management
"""

from fastapi import APIRouter

from .lens_artifact_routes import router as artifact_router
from .lens_chat_routes import router as chat_router
from .lens_state_routes import router as state_router

router = APIRouter(prefix="/api/v1/mindscape/lens", tags=["lens"])
router.include_router(state_router)
router.include_router(artifact_router)
router.include_router(chat_router)
