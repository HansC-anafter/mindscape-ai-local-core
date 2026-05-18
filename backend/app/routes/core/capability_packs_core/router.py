from fastapi import APIRouter

from .activation_routes import router as activation_router
from .installed_routes import router as installed_router

router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])
router.include_router(activation_router)
router.include_router(installed_router)
