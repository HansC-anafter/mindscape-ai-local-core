from fastapi import APIRouter

from . import authorize_routes, callback_routes, token_routes

router = APIRouter(prefix="/api/v1/runtime-oauth", tags=["runtime-oauth"])
router.include_router(authorize_routes.router)
router.include_router(callback_routes.router)
router.include_router(token_routes.router)
