"""Host runtime session gateway routes."""

from fastapi import APIRouter

from .rest_endpoints import router as rest_router
from .ws_endpoints import router as ws_router

router = APIRouter()
router.include_router(rest_router)
router.include_router(ws_router)
