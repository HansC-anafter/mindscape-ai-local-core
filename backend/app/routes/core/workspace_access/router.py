"""Thin router composition for access-control leaves."""

from fastapi import APIRouter

from .bootstrap_routes import router as bootstrap_router
from .invitation_routes import router as invitation_router
from .management_routes import router as management_router


router = APIRouter()
router.include_router(bootstrap_router)
router.include_router(invitation_router)
router.include_router(management_router)
