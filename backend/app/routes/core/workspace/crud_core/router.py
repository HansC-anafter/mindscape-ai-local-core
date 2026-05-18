
from fastapi import APIRouter

from . import create_routes, detail_routes, list_routes, playbook_config_routes

router = APIRouter()
router.include_router(list_routes.router)
router.include_router(create_routes.router)
router.include_router(detail_routes.router)
router.include_router(playbook_config_routes.router)
