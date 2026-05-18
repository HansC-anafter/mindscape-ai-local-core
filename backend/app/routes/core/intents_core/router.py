from fastapi import APIRouter

from . import detail_routes, list_routes

router = APIRouter(prefix="/api/v1", tags=["intents"])
router.include_router(list_routes.router)
router.include_router(detail_routes.router)
