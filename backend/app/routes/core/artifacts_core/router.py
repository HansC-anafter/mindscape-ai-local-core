
from fastapi import APIRouter

from . import detail_routes, file_routes, followup_routes, list_routes

router = APIRouter(prefix="/api/v1", tags=["artifacts"])
router.include_router(list_routes.router)
router.include_router(detail_routes.router)
router.include_router(followup_routes.router)
router.include_router(file_routes.router)
