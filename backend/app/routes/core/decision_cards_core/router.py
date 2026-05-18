from fastapi import APIRouter

from . import break_glass_routes, card_routes

router = APIRouter(prefix="/api/v1/workspaces", tags=["decision-cards"])
router.include_router(card_routes.router)
router.include_router(break_glass_routes.router)
