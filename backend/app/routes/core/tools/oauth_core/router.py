from fastapi import APIRouter

from . import authorize_routes, refresh_routes

router = APIRouter(prefix="/api/v1/tools/oauth", tags=["tools", "oauth"])
router.include_router(authorize_routes.router)
router.include_router(refresh_routes.router)
