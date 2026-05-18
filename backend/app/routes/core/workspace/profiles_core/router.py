
from fastapi import APIRouter

from . import control_preset_routes, control_routes, runtime_preset_routes, runtime_routes

router = APIRouter()
router.include_router(runtime_routes.router)
router.include_router(runtime_preset_routes.router)
router.include_router(control_routes.router)
router.include_router(control_preset_routes.router)
