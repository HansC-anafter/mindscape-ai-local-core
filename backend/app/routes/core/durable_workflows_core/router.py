"""Thin composition for durable workflow review route leaves."""

from fastapi import APIRouter

from . import command_routes, read_routes

router = APIRouter(prefix="/api/v1", tags=["durable-workflows"])
router.include_router(read_routes.router)
router.include_router(command_routes.router)
