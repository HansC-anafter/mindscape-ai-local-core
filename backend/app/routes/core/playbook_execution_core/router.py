from fastapi import APIRouter

from . import control_routes, debug_routes, lifecycle_routes, read_routes

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbook-execution"])
router.include_router(debug_routes.router)
router.include_router(control_routes.router)
router.include_router(read_routes.router)
router.include_router(lifecycle_routes.router)
